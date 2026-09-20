# acc-migrate — engineering rules for Claude Code

You are building ACC's Databricks → AWS-native migration accelerator. Read this file fully before any change.

## What this repo is
Deterministic MCP servers (`servers/*-mcp`) that migrate Databricks/Unity Catalog estates to S3 + Iceberg + Glue + Lake Formation, plus a thin agent layer on Amazon Bedrock AgentCore. Everything deploys into a client's AWS account. Full context: `docs/BUILD_PLAN.md`, `docs/PLATFORM_DESIGN.md`.

## Non-negotiable rules
1. **Spec first.** Every server has a `SPEC.md`. Build strictly to it. If the spec is ambiguous, append the question to `OPEN_QUESTIONS.md` in that server and implement the option with no side effects.
2. **Never write to source systems.** No code path may write to Databricks, Unity Catalog or source S3 prefixes. No `INSERT/ALTER/DROP/CREATE` against Databricks. Any PR touching `promote.py`, `aws-mcp`, or IAM Terraform needs two human reviewers — add the `needs-two-reviewers` label.
3. **No static credentials, ever.** Secrets come from AWS Secrets Manager at runtime. OIDC for CI. If you find a key in code, stop and report it.
4. **Log counts, hashes and paths — never data values.** No sampled rows in logs, exceptions or test output committed to the repo.
5. **Golden fixtures are never generated from the code under test.** Expected results come from the Databricks fixture workspace, recorded once and committed under `tests/fixtures/expected/`.
6. **Idempotent and resumable.** Every long-running operation has a manifest and converges on re-run.
7. **Every strategy rule and every type mapping has a named unit test** (`test_strategy_rule_<id>`, `test_type_map_<delta_type>`).
8. **Encryption is not optional.** Refuse to run any S3 write without a KMS CMK ARN in options.

## Stack and conventions
- Python 3.12, `uv` for deps (`uv sync`, `uv run`), pinned versions in `pyproject.toml`.
- Lint/type: `ruff check .`, `ruff format .`, `mypy --strict src/`. All must pass before you say a task is done.
- Tests: `pytest -q` for unit; `pytest -m integration` needs `AWS_PROFILE=acc-sandbox`. Coverage gate 80% overall, 90% on `strategy.py`, `types.py`, `partitioning.py`.
- MCP servers use the official Python MCP SDK; `server.py` registers tools only, no logic. All I/O models are Pydantic in `schemas.py`.
- Spark jobs live in `spark_jobs/`, run on EMR Serverless, and are also runnable locally with `pyspark` for tests.
- Terraform ≥1.9, modules under `infra/terraform/modules/`, `checkov` must be clean.
- Structured JSON logging via `structlog`; OpenTelemetry spans on every tool call, tagged `run_id`, `table_ref`.
- Commit messages: conventional commits (`feat(table-mcp): ...`). Small PRs, one concern each.

## Workflow you must follow for any feature
1. Read the server's `SPEC.md` section for the feature.
2. Write or update the acceptance/unit tests first, from the spec.
3. Implement until tests, ruff, mypy pass.
4. Run `/security-review` (sub-agent) on the diff.
5. Update `docs/adr/` if you made a design decision not in the spec.
6. Summarise what you built against which spec section in the PR description.

## Definition of done for any PR
- Spec section referenced; tests added; ruff/mypy/pytest green; checkov green if Terraform touched; no data values in logs; security review comment present; ADR if needed.

## When to stop and ask a human
- Anything that would require a write grant on the source.
- A spec conflict you cannot resolve with the no-side-effects rule.
- Adding a dependency with a non-permissive licence (GPL/AGPL/SSPL).
- Any change to IAM policies or KMS usage.
