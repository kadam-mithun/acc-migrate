# table-mcp — server rules (extends root CLAUDE.md) — v0.3

- Build strictly to `SPEC.md` v0.3. Strategy decision order is S6 → S7 → S5 → S4 → S3 → S2 → S1; never reorder.
- Data files are read directly from S3 via the Delta log (`deltalake` / Delta Kernel). Zero DBU in the data path; discovery may use the minimal auto-stop SQL warehouse only.
- Startup self-check (`selfcheck.py`) must pass all three checks in SPEC §10 (Databricks effective privileges incl. inheritance/ownership, IAM policy simulation on source prefixes, staging/source disjointness). Failure is a hard stop.
- KMS enforcement is three-layer per SPEC §10 and ADR-0001: precondition on `options.kms_key_arn`, injected Spark and PyIceberg SSE-KMS config from `storage.py`, bucket policy in Terraform. Do not implement a wrapper-around-every-write.
- `promote.py` validates the approval record per SPEC §9.1. Two human reviewers on any change here.
- All logging goes through `redact.py`; never log column values, partition values, or unscrubbed library exceptions. Aggregates go only to the encrypted conversion record.
- Recovery of stale RUNNING cancels the EMR job run before any cleanup (SPEC §9). Spark jobs write only under attempt-scoped prefixes.
- Acceptance tests AT-01 … AT-22 in SPEC §11 are the definition of done; keep their IDs in test names. Integration/acceptance tests skip until `tests/fixtures/expected/` exists; strategy/type unit tests use the human-authored YAML oracles.
- Every strategy has `test_strategy_rule_<S>`, every trigger condition its own test, every order boundary its own test; every type mapping has `test_type_map_<delta_type>`.
