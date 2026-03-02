#!/usr/bin/env python3
"""MCP server for OpenAlex quantum publication statistics."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from openalex_core import (
    DEFAULT_HISTORY_YEARS,
    quantum_publication_stats_custom_range_data,
    quantum_publication_stats_data,
)

mcp = FastMCP("openalex-quantum-stats")


@mcp.tool()
def quantum_publication_stats(
    history_years: int = DEFAULT_HISTORY_YEARS,
    include_previous_years: bool = True,
) -> Dict[str, Any]:
    """Return quantum-related publication counts for UK, US, Europe, and China."""
    return quantum_publication_stats_data(
        history_years=history_years,
        include_previous_years=include_previous_years,
    )


@mcp.tool()
def quantum_publication_stats_custom_range(start_year: int, end_year: int) -> Dict[str, Any]:
    """Return quantum publication counts for each year in a custom inclusive year range."""
    return quantum_publication_stats_custom_range_data(start_year=start_year, end_year=end_year)


if __name__ == "__main__":
    mcp.run()
