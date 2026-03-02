#!/usr/bin/env python3
"""Core OpenAlex query logic shared by MCP server, CLI, and dashboard."""

from __future__ import annotations

import datetime as dt
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import requests

OPENALEX_API_BASE = "https://api.openalex.org"
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_HISTORY_YEARS = 6
DEFAULT_MAX_QUANTUM_CONCEPTS = 25

# Country code sets for filters. Europe intentionally excludes GB.
REGION_COUNTRY_CODES: Dict[str, List[str]] = {
    "uk": ["gb"],
    "us": ["us"],
    "china": ["cn"],
    "europe": [
        "al", "ad", "at", "by", "be", "ba", "bg", "hr", "cy", "cz", "dk",
        "ee", "fi", "fr", "de", "gr", "hu", "is", "ie", "it", "lv", "li",
        "lt", "lu", "mt", "md", "mc", "me", "nl", "mk", "no", "pl", "pt",
        "ro", "ru", "sm", "rs", "sk", "si", "es", "se", "ch", "ua", "va",
    ],
}

REGION_LABELS = {
    "uk": "United Kingdom",
    "us": "United States",
    "europe": "Europe (excluding UK)",
    "china": "China",
}

QUANTUM_SEED_SEARCH_TERMS = [
    "quantum physics",
    "quantum computing",
    "quantum information",
    "quantum communication",
    "quantum cryptography",
    "quantum sensing",
    "quantum optics",
    "quantum algorithm",
    "qubit",
]

QUANTUM_INCLUDE_NAME_SNIPPETS = [
    "quantum",
    "qubit",
]

QUANTUM_PRIORITY_SNIPPETS = [
    "quantum computing",
    "quantum information",
    "quantum communication",
    "quantum cryptography",
    "quantum sensing",
    "quantum optics",
    "quantum algorithm",
    "qubit",
]


@dataclass
class OpenAlexClient:
    mailto: str | None = None
    delay_seconds: float = 0.12

    def __post_init__(self) -> None:
        self.session = requests.Session()

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        base = {"per-page": 1}
        base.update(params)
        if self.mailto:
            base["mailto"] = self.mailto

        response = self.session.get(
            f"{OPENALEX_API_BASE}{path}",
            params=base,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        time.sleep(self.delay_seconds)
        response.raise_for_status()
        return response.json()

    def resolve_quantum_concept_id(self) -> str:
        configured = os.getenv("OPENALEX_QUANTUM_CONCEPT_ID")
        if configured:
            return configured

        payload = self._get("/concepts", {"search": "quantum physics", "per-page": 10})
        results = payload.get("results", [])
        for concept in results:
            name = str(concept.get("display_name", "")).lower()
            if "quantum" in name:
                concept_id = concept.get("id", "")
                if concept_id:
                    return concept_id.rsplit("/", 1)[-1]

        if results and results[0].get("id"):
            return results[0]["id"].rsplit("/", 1)[-1]

        raise RuntimeError("Could not resolve a quantum concept ID from OpenAlex")

    def resolve_quantum_concepts_broad(self, max_ids: int = DEFAULT_MAX_QUANTUM_CONCEPTS) -> List[Dict[str, Any]]:
        configured = os.getenv("OPENALEX_QUANTUM_CONCEPT_IDS")
        if configured:
            ids = [cid.strip() for cid in configured.split(",") if cid.strip()]
            if ids:
                return [{"id": cid, "display_name": cid, "works_count": 0} for cid in ids[:max_ids]]

        concept_map: Dict[str, Dict[str, Any]] = {}
        for term in QUANTUM_SEED_SEARCH_TERMS:
            payload = self._get("/concepts", {"search": term, "per-page": 25})
            for concept in payload.get("results", []):
                concept_id_raw = str(concept.get("id", ""))
                if not concept_id_raw:
                    continue
                concept_id = concept_id_raw.rsplit("/", 1)[-1]
                name = str(concept.get("display_name", "")).lower()
                if any(snippet in name for snippet in QUANTUM_INCLUDE_NAME_SNIPPETS):
                    concept_map[concept_id] = concept

        if not concept_map:
            fallback_id = self.resolve_quantum_concept_id()
            return [{"id": fallback_id, "display_name": fallback_id, "works_count": 0}]

        prioritized: List[tuple[int, int, str]] = []
        for concept_id, concept in concept_map.items():
            name = str(concept.get("display_name", "")).lower()
            works_count = int(concept.get("works_count", 0) or 0)
            priority = 0
            for idx, snippet in enumerate(QUANTUM_PRIORITY_SNIPPETS):
                if snippet in name:
                    priority = len(QUANTUM_PRIORITY_SNIPPETS) - idx
                    break
            prioritized.append((priority, works_count, concept_id))

        prioritized.sort(reverse=True)
        selected_ids = [concept_id for _, _, concept_id in prioritized[:max_ids]]
        return [
            {
                "id": concept_id,
                "display_name": concept_map[concept_id].get("display_name", concept_id),
                "works_count": int(concept_map[concept_id].get("works_count", 0) or 0),
            }
            for concept_id in selected_ids
        ]

    def resolve_quantum_concept_ids_broad(self, max_ids: int = DEFAULT_MAX_QUANTUM_CONCEPTS) -> List[str]:
        return [c["id"] for c in self.resolve_quantum_concepts_broad(max_ids=max_ids)]

    def count_works(self, filters: List[str], search: str | None = None) -> int:
        params: Dict[str, Any] = {"filter": ",".join(filters)}
        if search:
            params["search"] = search
        payload = self._get("/works", params)
        return int(payload.get("meta", {}).get("count", 0))


def year_bounds(year: int) -> tuple[str, str]:
    return f"{year}-01-01", f"{year}-12-31"


def country_filter_for(region: str) -> str:
    country_codes = REGION_COUNTRY_CODES[region]
    if len(country_codes) == 1:
        return f"authorships.institutions.country_code:{country_codes[0]}"
    return "authorships.institutions.country_code:" + "|".join(country_codes)


def concepts_filter_for_ids(concept_ids: List[str]) -> str:
    unique_ids = []
    seen = set()
    for concept_id in concept_ids:
        if concept_id not in seen:
            seen.add(concept_id)
            unique_ids.append(concept_id)
    return "concepts.id:" + "|".join(unique_ids)


def build_yearly_series(
    client: OpenAlexClient,
    concept_filter: str,
    region: str,
    start_year: int,
    end_year: int,
) -> Dict[str, int]:
    series: Dict[str, int] = {}
    region_filter = country_filter_for(region)

    for year in range(start_year, end_year + 1):
        start_date, end_date = year_bounds(year)
        total = client.count_works(
            filters=[
                concept_filter,
                region_filter,
                f"from_publication_date:{start_date}",
                f"to_publication_date:{end_date}",
            ]
        )
        series[str(year)] = total

    return series


def build_summary(series: Dict[str, int], last_year: int) -> Dict[str, Any]:
    values = list(series.values())
    if not values:
        return {"last_year": last_year, "last_year_count": 0, "avg_per_year": 0.0, "total": 0}

    return {
        "last_year": last_year,
        "last_year_count": series.get(str(last_year), 0),
        "avg_per_year": round(sum(values) / len(values), 2),
        "total": sum(values),
    }


def quantum_publication_stats_data(
    history_years: int = DEFAULT_HISTORY_YEARS,
    include_previous_years: bool = True,
) -> Dict[str, Any]:
    history_years = max(1, min(history_years, 25))
    last_complete_year = dt.datetime.now(dt.timezone.utc).year - 1
    start_year = last_complete_year - history_years + 1

    client = OpenAlexClient(mailto=os.getenv("OPENALEX_MAILTO"))
    concept_ids = client.resolve_quantum_concept_ids_broad()
    concept_filter = concepts_filter_for_ids(concept_ids)

    regions_output: Dict[str, Any] = {}
    for region in ["uk", "us", "europe", "china"]:
        if include_previous_years:
            series = build_yearly_series(client, concept_filter, region, start_year, last_complete_year)
        else:
            series = build_yearly_series(client, concept_filter, region, last_complete_year, last_complete_year)

        regions_output[region] = {
            "label": REGION_LABELS[region],
            "summary": build_summary(series, last_complete_year),
            "yearly_counts": series,
        }

    return {
        "query": {
            "topic": "quantum-related papers (broad concept family)",
            "concept_ids": concept_ids,
            "last_complete_year": last_complete_year,
            "start_year": start_year if include_previous_years else last_complete_year,
            "end_year": last_complete_year,
            "regions": [REGION_LABELS[r] for r in ["uk", "us", "europe", "china"]],
            "notes": [
                "A paper is counted for a region if at least one listed institution has a country code in that region.",
                "Counts can overlap across regions when papers have international co-authorship.",
            ],
        },
        "regions": regions_output,
    }


def quantum_publication_stats_custom_range_data(start_year: int, end_year: int) -> Dict[str, Any]:
    current_year = dt.datetime.now(dt.timezone.utc).year
    if start_year < 1900 or end_year > current_year or start_year > end_year:
        raise ValueError(
            f"Invalid year range [{start_year}, {end_year}]. Expected 1900 <= start_year <= end_year <= {current_year}."
        )

    client = OpenAlexClient(mailto=os.getenv("OPENALEX_MAILTO"))
    concept_ids = client.resolve_quantum_concept_ids_broad()
    concept_filter = concepts_filter_for_ids(concept_ids)

    regions_output: Dict[str, Any] = {}
    for region in ["uk", "us", "europe", "china"]:
        series = build_yearly_series(client, concept_filter, region, start_year, end_year)
        regions_output[region] = {
            "label": REGION_LABELS[region],
            "summary": {
                "start_year": start_year,
                "end_year": end_year,
                "total": sum(series.values()),
                "avg_per_year": round(sum(series.values()) / len(series), 2),
            },
            "yearly_counts": series,
        }

    return {
        "query": {
            "topic": "quantum-related papers (broad concept family)",
            "concept_ids": concept_ids,
            "start_year": start_year,
            "end_year": end_year,
            "regions": [REGION_LABELS[r] for r in ["uk", "us", "europe", "china"]],
        },
        "regions": regions_output,
    }
