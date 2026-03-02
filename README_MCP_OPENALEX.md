# OpenAlex MCP Server

This server exposes MCP tools that fetch publication counts from OpenAlex for:
- United Kingdom
- United States
- Europe (excluding UK)
- China

## Tools
- `quantum_publication_stats(history_years=6, include_previous_years=True)`
  - Returns last complete year and optional previous years.
- `quantum_publication_stats_custom_range(start_year, end_year)`
  - Returns yearly counts for a custom inclusive range.
  - Uses a broad quantum concept family (computing, communication/cryptography, sensing, optics, information, qubit-related concepts).

## Setup
1. Install dependencies:
   ```bash
   pip install mcp requests streamlit pandas
   ```
2. Optional environment variables:
   - `OPENALEX_MAILTO=you@example.com` (recommended for OpenAlex polite pool)
   - `OPENALEX_QUANTUM_CONCEPT_ID=C123456789` (override auto-resolved concept)
   - `OPENALEX_QUANTUM_CONCEPT_IDS=C1,C2,C3` (override broad concept set)

## Run MCP server
```bash
python mcp_openalex_server.py
```

## Run CLI (table/JSON)
```bash
python stats.py
python stats.py --last-year-only
python stats.py --start-year 2020 --end-year 2025
python stats.py --start-year 2015 --end-year 2025 --json
```

## Run interactive chart dashboard
```bash
streamlit run dashboard.py
```

Dashboard selectors:
- Topic: All research papers or Quantum-related papers
- Year range
- Regions (UK, US, Europe, China)

Dashboard outputs:
- Region yearly trend and totals
- Quantum concept breakdown table (Concept ID + Concept name + per-year counts) when the quantum topic is selected

## Notes on counting
- A work is counted for a region if any listed institution country is in that region.
- Counts can overlap across regions due to international co-authorship.
