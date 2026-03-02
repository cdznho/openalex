#!/usr/bin/env python3
"""Interactive dashboard for OpenAlex publication stats by region."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from openalex_core import (
    OpenAlexClient,
    REGION_COUNTRY_CODES,
    REGION_LABELS,
    build_yearly_series,
    concepts_filter_for_ids,
    country_filter_for,
)

REGION_ORDER = ["uk", "us", "europe", "china"]
TOPIC_OPTIONS = {
    "All research papers": None,
    "Quantum-related papers (broad)": "quantum_broad",
}


@st.cache_data(ttl=24 * 60 * 60)
def fetch_region_series(topic_key: str, start_year: int, end_year: int) -> Dict[str, Dict[str, int]]:
    client = OpenAlexClient()
    concept_filter = None

    if TOPIC_OPTIONS[topic_key] == "quantum_broad":
        concept_ids = client.resolve_quantum_concept_ids_broad()
        concept_filter = concepts_filter_for_ids(concept_ids)

    result: Dict[str, Dict[str, int]] = {}
    for region in REGION_ORDER:
        if concept_filter:
            series = build_yearly_series(client, concept_filter, region, start_year, end_year)
        else:
            series = {}
            region_filter = country_filter_for(region)
            for year in range(start_year, end_year + 1):
                total = client.count_works(
                    filters=[
                        region_filter,
                        f"from_publication_date:{year}-01-01",
                        f"to_publication_date:{year}-12-31",
                    ]
                )
                series[str(year)] = total

        result[region] = series

    return result


def series_to_dataframe(series_map: Dict[str, Dict[str, int]], selected_regions: List[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for region in selected_regions:
        label = REGION_LABELS[region]
        for year_str, count in series_map[region].items():
            rows.append({"Year": int(year_str), "Region": label, "Papers": int(count)})

    return pd.DataFrame(rows).sort_values(["Year", "Region"])


@st.cache_data(ttl=24 * 60 * 60)
def fetch_quantum_concept_yearly_breakdown(
    start_year: int, end_year: int, selected_regions: tuple[str, ...]
) -> pd.DataFrame:
    client = OpenAlexClient()
    concepts = client.resolve_quantum_concepts_broad()

    country_codes: List[str] = []
    seen = set()
    for region in selected_regions:
        for code in REGION_COUNTRY_CODES[region]:
            if code not in seen:
                seen.add(code)
                country_codes.append(code)

    if len(country_codes) == 1:
        region_filter = f"authorships.institutions.country_code:{country_codes[0]}"
    else:
        region_filter = "authorships.institutions.country_code:" + "|".join(country_codes)

    rows: List[Dict[str, Any]] = []
    for concept in concepts:
        concept_id = concept["id"]
        concept_name = concept.get("display_name", concept_id)
        for year in range(start_year, end_year + 1):
            total = client.count_works(
                filters=[
                    f"concepts.id:{concept_id}",
                    region_filter,
                    f"from_publication_date:{year}-01-01",
                    f"to_publication_date:{year}-12-31",
                ]
            )
            rows.append(
                {
                    "Concept ID": concept_id,
                    "Concept": concept_name,
                    "Year": year,
                    "Papers": total,
                }
            )

    return pd.DataFrame(rows)


@st.cache_data(ttl=24 * 60 * 60)
def fetch_quantum_concepts() -> pd.DataFrame:
    client = OpenAlexClient()
    concepts = client.resolve_quantum_concepts_broad()
    rows: List[Dict[str, Any]] = []
    for concept in concepts:
        rows.append(
            {
                "Concept ID": concept["id"],
                "Concept": concept.get("display_name", concept["id"]),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="OpenAlex Publication Stats", layout="wide")
    st.title("OpenAlex Publication Stats")
    st.caption("UK, US, Europe (excluding UK), and China")

    current_year = dt.datetime.now(dt.timezone.utc).year
    last_complete_year = current_year - 1

    with st.sidebar:
        st.header("Filters")
        topic = st.selectbox("Topic", list(TOPIC_OPTIONS.keys()), index=0)

        start_default = max(2000, last_complete_year - 5)
        year_range = st.slider(
            "Year range",
            min_value=1900,
            max_value=last_complete_year,
            value=(start_default, last_complete_year),
            step=1,
        )

        region_labels = {REGION_LABELS[k]: k for k in REGION_ORDER}
        selected_region_labels = st.multiselect(
            "Regions",
            options=list(region_labels.keys()),
            default=list(region_labels.keys()),
        )

    selected_regions = [region_labels[label] for label in selected_region_labels]
    start_year, end_year = year_range

    if not selected_regions:
        st.warning("Select at least one region.")
        return

    with st.spinner("Fetching data from OpenAlex..."):
        series_map = fetch_region_series(topic, start_year, end_year)

    df = series_to_dataframe(series_map, selected_regions)

    st.subheader("Yearly trend")
    st.line_chart(df, x="Year", y="Papers", color="Region")

    last_year_df = df[df["Year"] == end_year][["Region", "Papers"]].sort_values("Papers", ascending=False)
    st.subheader(f"Latest year snapshot ({end_year})")
    st.dataframe(last_year_df, use_container_width=True, hide_index=True)

    pivot = df.pivot(index="Year", columns="Region", values="Papers").fillna(0).astype(int)
    st.subheader("Yearly counts")
    st.dataframe(pivot, use_container_width=True)

    if TOPIC_OPTIONS[topic] == "quantum_broad":
        concept_list_df = fetch_quantum_concepts()
        with st.expander("Active quantum concept codes", expanded=False):
            st.dataframe(concept_list_df, use_container_width=True, hide_index=True)

        st.subheader("Quantum concept breakdown by year")
        with st.spinner("Fetching per-concept yearly counts..."):
            concept_df = fetch_quantum_concept_yearly_breakdown(
                start_year=start_year,
                end_year=end_year,
                selected_regions=tuple(selected_regions),
            )

        concept_pivot = (
            concept_df.pivot_table(
                index=["Concept ID", "Concept"],
                columns="Year",
                values="Papers",
                aggfunc="sum",
            )
            .fillna(0)
            .astype(int)
            .sort_values(by=end_year, ascending=False)
        )
        st.dataframe(concept_pivot, use_container_width=True)


if __name__ == "__main__":
    main()
