#!/usr/bin/env python3
"""CLI for OpenAlex quantum publication statistics."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from mcp_openalex_server import (
    quantum_publication_stats,
    quantum_publication_stats_custom_range,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch quantum-related publication counts from OpenAlex for UK, US, Europe, and China."
    )
    parser.add_argument(
        "--history-years",
        type=int,
        default=6,
        help="Number of years to include (ending at last complete year). Default: 6",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        help="Custom range start year (inclusive).",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        help="Custom range end year (inclusive).",
    )
    parser.add_argument(
        "--last-year-only",
        action="store_true",
        help="Return only last complete year counts.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output instead of a table.",
    )
    return parser.parse_args()


def format_table(payload: Dict[str, Any]) -> str:
    query = payload["query"]
    regions = payload["regions"]
    start_year = query["start_year"]
    end_year = query["end_year"]

    years = [str(y) for y in range(start_year, end_year + 1)]

    headers = ["Region", *years, "Total", "Avg/Year"]
    rows = []

    for region in ["uk", "us", "europe", "china"]:
        region_data = regions[region]
        yearly = region_data["yearly_counts"]
        summary = region_data["summary"]
        total = summary.get("total", sum(yearly.values()))
        avg = summary.get("avg_per_year", 0)

        row = [
            region_data["label"],
            *[str(yearly.get(y, 0)) for y in years],
            str(total),
            str(avg),
        ]
        rows.append(row)

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def render_row(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    sep = "-+-".join("-" * w for w in widths)

    concept_ref = query.get("concept_id") or ",".join(query.get("concept_ids", []))
    lines = [
        f"Topic: {query['topic']} ({concept_ref})",
        f"Years: {start_year}-{end_year}",
        "",
        render_row(headers),
        sep,
    ]
    lines.extend(render_row(r) for r in rows)
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    has_custom_start = args.start_year is not None
    has_custom_end = args.end_year is not None

    if has_custom_start != has_custom_end:
        print("Error: --start-year and --end-year must be provided together.", file=sys.stderr)
        return 2

    try:
        if has_custom_start and has_custom_end:
            payload = quantum_publication_stats_custom_range(args.start_year, args.end_year)
        else:
            payload = quantum_publication_stats(
                history_years=args.history_years,
                include_previous_years=not args.last_year_only,
            )
    except Exception as exc:
        print(f"Error fetching OpenAlex stats: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_table(payload))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
