# First Claude Code sessions — copy these prompts in order

## Session 0 — orientation (10 min)
> Read CLAUDE.md, docs/BUILD_PLAN.md section 0 and 6, docs/PLATFORM_DESIGN.md section 2, and servers/table-mcp/SPEC.md in full. Summarise back to me: the five rules you consider hardest to comply with, and any spec ambiguity you already see. Do not write code yet.

## Session 1 — scaffold table-mcp
> Use the new-mcp-server skill to scaffold servers/table-mcp exactly to SPEC.md section 13. Create Pydantic models in schemas.py for every tool in section 3 and the ConversionRecord in section 10. Register the tools in server.py with no logic. Add acceptance test stubs AT-01 to AT-22 as skipped tests with their pass criteria in the docstrings. Run uv sync, ruff, mypy, pytest and show me the output.

## Session 2 — strategy engine (pure functions first)
> Implement TableProfile and the strategy engine in strategy.py per SPEC.md section 5, decision order S6 → S7 → S5 → S4 → S3 → S2 → S1. Use the new-strategy-rule skill for each rule. Implement types.py with the exhaustive Delta→Iceberg type mapping and partitioning.py. Write the named unit tests first; target ≥ 90% coverage on these three files. Then run the spec-reviewer sub-agent on the diff and address blocking items.

## Session 3 — profiling from the Delta log
> Implement discover.py (Unity Catalog system tables via the Databricks SQL statement API, read-only) and profile.py (deltalake library reading the Delta log directly from S3). Include the startup self-check that fails if any write grant exists. Mock S3 and Databricks in unit tests with moto and recorded responses. Run security-reviewer on the diff.

## Session 4 — S1 metadata-only conversion end to end
> Implement convert/s1_snapshot.py with PyIceberg add_files, glue.py registration with the acc.* table properties, storage.py (KMS precondition and Spark/PyIceberg SSE-KMS config builders per SPEC §10 and ADR-0001), redact.py, selfcheck.py, the DynamoDB manifest with heartbeat/lease in ledger.py and locks.py, and validate.py inline checks from section 8. Make AT-01, AT-11, AT-12, AT-13, AT-15, AT-17, AT-18 runnable against the sandbox (pytest -m integration). Show me the conversion record JSON for trades_plain.

## Session 5 — Terraform and CI
> Write terraform/modules/table-mcp-role and table-mcp-emr to SPEC.md section 10 with no wildcard resources. Run terraform fmt/validate and checkov; fix until clean. Confirm .github/workflows/ci.yml passes locally with act if available, otherwise explain any gap.

## Then, in order: S3 rewrite (AT-03, AT-04, AT-09, AT-10) → S2 replay (AT-02) → S5 DLT and S6 UniForm (AT-06, AT-07) → S4 CDF (AT-05) → S7 (AT-08) → AT-16 estate run.

## Standing instructions for every session
- Start with: "Read CLAUDE.md and the relevant SPEC.md section before changing anything."
- End with: "Run spec-reviewer and security-reviewer on the diff, then write the PR description referencing spec sections."
- Use `/clear` between unrelated tasks; keep one server per session.

## Parallel track — fsi-fixtures (start alongside Session 1; owner: harness engineer)
> Read tools/fsi-fixtures/SPEC.md. Implement `plan` (manifest generation from seed) and the Faker-based value generators for §4 with FX-01 and FX-03 tests. No cloud calls yet.
> Then: implement `generate --scale small` writing local Parquet; validate referential integrity (FX-04). Then `deploy-databricks` behind a `--dry-run` flag that prints every SDK call before any real deployment.

## gov-mcp — start after table-mcp Session 2 (owner: senior engineer, WS-E)
> Read servers/gov-mcp/SPEC.md fully, especially §6 and §13. Scaffold with the new-mcp-server skill. Implement the PolicyModel (§5) and the gap taxonomy as data (gaps/taxonomy.py) with one detect/resolve test stub per gap id. No extraction code yet.

## assess-mcp — start week 3 (owner: lead architect + WS-A engineer)
> Read servers/assess-mcp/SPEC.md fully. Scaffold with new-mcp-server. Implement `assumptions/` YAML schemas and loaders, then `scenarios/demand.py` and the three scenario modules as pure functions with AT-A03, AT-A04, AT-A05, AT-A09 as unit tests on a small hand-built demand fixture. No Databricks calls yet.
