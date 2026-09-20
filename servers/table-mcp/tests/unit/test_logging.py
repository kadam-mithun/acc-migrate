"""The logging chain is the mechanism behind "all log emission passes through
`redact.py`" (SPEC §10, server CLAUDE.md).

`redact_event` is an allow-list: a key reaches the renderer only if
`LOGGABLE_KEYS` or `LOGGABLE_SUFFIXES` admits it. These tests pin the two
properties that matter — allow-listed keys survive, everything else is reported
by name with its value dropped.
"""

from __future__ import annotations

import json

import structlog

from table_mcp.redact import (
    LOGGABLE_KEYS,
    configure_logging,
    get_logger,
    redact_event,
)


def _process(event_dict: dict[str, object]) -> dict[str, object]:
    return dict(redact_event(None, "info", dict(event_dict)))


def test_allow_listed_keys_survive() -> None:
    out = _process(
        {
            "event": "table staged",
            "run_id": "run-1",
            "table_ref": "meridian_fin.gl.trades_plain",
            "strategy": "S1",
            "row_count": 200_000_000,
            "file_set_hash": "8f3a1c",
            "duration_ms": 1234,
        }
    )
    assert out["run_id"] == "run-1"
    assert out["strategy"] == "S1"
    assert out["row_count"] == 200_000_000
    assert out["file_set_hash"] == "8f3a1c"
    assert out["duration_ms"] == 1234
    assert "redacted_keys" not in out


def test_unknown_keys_are_dropped_by_name_only() -> None:
    """Root rule 4: counts, hashes and paths — never data values."""
    out = _process(
        {
            "event": "validated",
            "run_id": "run-1",
            "trade_date": "2026-01-01",
            "account": "ACME-001",
            "sum_notional": "1234567.89",
        }
    )
    assert out["redacted_keys"] == ["account", "sum_notional", "trade_date"]
    rendered = json.dumps(out)
    for value in ("2026-01-01", "ACME-001", "1234567.89"):
        assert value not in rendered


def test_paths_are_withheld_until_redact_path_exists() -> None:
    """SPEC §10 permits *redacted* paths; `redact_path` is still a stub, so a raw
    path carrying partition values must not reach the renderer."""
    out = _process(
        {
            "event": "writing",
            "run_id": "run-1",
            "location": "s3://bucket/iceberg/staging/trade_date=2026-01-01/",
            "staging_prefix": "s3://bucket/iceberg/staging/",
        }
    )
    assert "location" not in out
    assert "staging_prefix" not in out
    assert "2026-01-01" not in json.dumps(out)


def test_tracebacks_and_raw_exceptions_never_render() -> None:
    """Library messages become an ErrorEnvelope; they are never logged raw."""
    out = _process(
        {
            "event": "failed",
            "run_id": "run-1",
            "exc_info": True,
            "exception": "AnalysisException: cannot resolve 'account_id' given 'ACME-001'",
        }
    )
    assert "exception" not in out
    assert "exc_info" not in out
    assert "ACME-001" not in json.dumps(out)


def test_configure_logging_installs_redaction_before_the_renderer() -> None:
    configure_logging()
    processors = structlog.get_config()["processors"]
    assert redact_event in processors
    assert processors.index(redact_event) == len(processors) - 2, (
        "redact_event must be the last processor before the renderer"
    )
    assert isinstance(processors[-1], structlog.processors.JSONRenderer)


def test_logger_emits_only_allow_listed_keys_end_to_end() -> None:
    configure_logging()
    captured = structlog.testing.CapturingLoggerFactory()
    structlog.configure(logger_factory=captured)

    get_logger("table_mcp.test").info(
        "table staged", run_id="run-1", row_count=10, account="ACME-001"
    )

    rendered = captured.logger.calls[0].args[0]
    assert "ACME-001" not in rendered
    payload = json.loads(rendered)
    assert payload["run_id"] == "run-1"
    assert payload["redacted_keys"] == ["account"]
    assert set(payload) <= LOGGABLE_KEYS | {"row_count"}
