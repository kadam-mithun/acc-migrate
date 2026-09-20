# gov-mcp — server rules (extends root CLAUDE.md)
- Build strictly to `SPEC.md`. Gap ids (G-xx-nn) are stable identifiers; never renumber or reuse.
- This server PROPOSES. Never add `lakeformation:Grant*`/`Revoke*` or any apply path; `request_apply` only writes to the ledger.
- Every gap id has `test_gap_<id>_detect` and `test_gap_<id>_resolve`.
- Masking/filter SQL bodies are untrusted: parse with SQLGlot, never execute, never interpolate unescaped.
- On any ambiguity emit the MORE restrictive translation and add an `OPEN_QUESTIONS.md` entry.
- Section 13 decisions are binding: tiered masked views (G-CM-02), enumerated filters + drift (G-RL-02), strict_sensitive=true, detect-and-block IAMAllowedPrincipals (G-TG-05), IdC groups default, 90-day snapshot retention.
- Rego policies under `policies/` are shared with the Compliance Agent; changes need security-lead review.
