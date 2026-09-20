# fsi-fixtures — rules (extends root CLAUDE.md)
- Zero real data. Every value from Faker or a deterministic function of the seed. No external datasets, no network reads except Databricks/AWS APIs.
- PANs: Luhn-valid, test IIN ranges only. LEIs/BICs: synthetic, checksum-valid.
- `snapshot-golden` outputs are recorded ONCE; changing them requires a PR with reviewer approval and an OPEN_QUESTIONS entry in the consuming server.
- Named fixtures in SPEC §3 must exist exactly as specified; FX-02 asserts this.
- Emit PROVENANCE.md on every run.
