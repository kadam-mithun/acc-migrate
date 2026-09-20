# `table-mcp`

Delta Lake → Apache Iceberg conversion service. Build specification: `SPEC.md`
(v0.3.1). Server rules: `CLAUDE.md`. Open questions: `OPEN_QUESTIONS.md`.

Read-only against Databricks, Unity Catalog and the source S3 prefixes. Runs
entirely inside the client's AWS account.

## Status

Scaffold. The I/O contract (`schemas.py`), the tool registration (`server.py`)
and the test skeleton exist; the domain modules are stubs that raise
`NotImplementedError` against their SPEC section, and the acceptance tests
AT-01 … AT-22 are skipped stubs carrying their pass criteria.

## Layout

Per SPEC §13:

```
src/table_mcp/
  server.py        MCP tool registration only, no logic
  schemas.py       Pydantic models for every input and output
  discover.py profile.py strategy.py types.py partitioning.py
  convert/         s1_snapshot s2_replay s3_rewrite s4_cdf s6_bridge
  glue.py validate.py promote.py ledger.py locks.py
  telemetry.py storage.py redact.py selfcheck.py
schemas/           approval_record.json, conversion_record.json
spark_jobs/        rewrite_job.py, cdf_job.py
terraform/modules/ table-mcp-role, table-mcp-emr  (gated on human approval)
tests/             unit/ integration/ acceptance/ fixtures/
```

## Working on it

```sh
uv sync --extra dev
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src tools
uv run python tools/check_log_calls.py src spark_jobs tests   # logging rule (c)
uv run pytest -q
PYTHONPATH=src uv run python -m table_mcp.schemas   # regenerate schemas/*.json
```

**macOS note.** `uv` marks `.venv` hidden, files inside inherit the flag, and
CPython's `site.py` silently skips a hidden `.pth` — so the editable install of
this package does not take effect and `import table_mcp` fails outside pytest.
The test suite is immune (`pythonpath = ["src"]` in `pyproject.toml`); for
ad-hoc commands either prefix `PYTHONPATH=src` as above, or clear the flag once
with `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` (any `uv sync`
re-sets it). Linux CI is unaffected.

Integration tests need `AWS_PROFILE=acc-sandbox`; acceptance tests stay skipped
until the golden fixtures are recorded into `tests/fixtures/expected/` by
`fsi-fixtures snapshot-golden` (SPEC §11). Golden fixtures are never generated
from this code.
