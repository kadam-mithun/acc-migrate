---
name: new-mcp-server
description: Scaffold a new deterministic MCP server under servers/<name>-mcp following ACC conventions (Pydantic schemas, tool registration, telemetry, ledger, tests, Terraform role module).
---
# New MCP server

When asked to create `servers/<name>-mcp`:
1. Read `servers/table-mcp/` as the reference implementation and `CLAUDE.md`.
2. Create the layout:
   ```
   servers/<name>-mcp/
     SPEC.md  CLAUDE.md  OPEN_QUESTIONS.md  pyproject.toml  README.md
     src/<name>_mcp/{__init__,server,schemas,ledger,telemetry,errors}.py
     tests/{unit,integration,acceptance}/  tests/fixtures/expected/
     terraform/modules/<name>-mcp-role/{main,variables,outputs}.tf
   ```
3. `server.py`: register tools from the spec's interface table only; each handler validates input with the Pydantic model, opens an OTel span tagged with `run_id`, calls a function in a domain module, wraps errors in `ErrorEnvelope`.
4. `schemas.py`: one Pydantic model per tool input and output; `ErrorEnvelope {code, message, retryable, hint, table?}`.
5. `ledger.py`: `write_record(run_id, subject, record: dict)` to the DynamoDB run table and S3 evidence prefix; never include data values.
6. Terraform role module: least-privilege per SPEC section on security; no wildcards on resources; `checkov` clean.
7. Tests: one acceptance test stub per row of the spec's acceptance table, marked `@pytest.mark.acceptance` and skipped until fixtures exist; unit tests for schemas and error wrapping.
8. Run `uv sync && ruff check . && mypy --strict src && pytest -q` and report.
