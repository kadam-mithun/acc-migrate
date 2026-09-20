# assess-mcp — server rules (extends root CLAUDE.md)
- Metadata only. Never add `SELECT` on any catalog other than `system`, and never `s3:GetObject` on data prefixes. Startup self-check enforces this.
- Query text is hashed (xxhash64) and parsed for shape before any persistence; raw text is never stored or logged.
- All prices, ratios, rates and thresholds live in `assumptions/` and `rules/` YAML with schema validation; no numeric literals in scenario code.
- Stay, federate and exit share `scenarios/demand.py`; no scenario-specific demand adjustments.
- Every cost is P10/P50/P90; every recommendation states its flip conditions.
- Determinism: same snapshot + versions → identical JSON (AT-A09).
