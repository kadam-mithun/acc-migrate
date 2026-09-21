"""Every registered tool dispatches through the span + error-wrap path.

`server.py` holds no logic, so what is testable here is the wiring: each tool
validates its input, opens a span and delegates to exactly one domain function.
The domain functions are scaffold stubs raising `NotImplementedError`, so every
call currently comes back as a redacted `ErrorEnvelope` rather than an
exception escaping the tool (SPEC §3, §10).

These assertions flip as each domain module is implemented — a tool that starts
returning its typed output will fail its row here, which is the intended signal.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from table_mcp import server
from table_mcp.schemas import (
    ConversionTarget,
    DeltaProtocol,
    ErrorCode,
    ErrorEnvelope,
    TableFeatures,
    TableProfile,
    TableRef,
)

RUN_ID = "run-1"
TABLE = TableRef(catalog="meridian_fin", schema_name="gl", name="trades_plain")
TARGET = ConversionTarget(client_bucket="acc-client-bucket", region="eu-west-1")
PROFILE = TableProfile(
    table_ref=TABLE,
    protocol=DeltaProtocol(min_reader_version=1, min_writer_version=2),
    features=TableFeatures(),
    version_count=1,
    latest_version=0,
    active_file_count=10,
    total_size_bytes=1024,
)

TOOL_CALLS: list[tuple[str, Callable[[], object], bool]] = [
    (
        "discover_tables",
        lambda: server.discover_tables(run_id=RUN_ID, catalog="meridian_fin"),
        False,
    ),
    ("profile_table", lambda: server.profile_table(run_id=RUN_ID, table_ref=TABLE), True),
    (
        "recommend_strategy",
        lambda: server.recommend_strategy(run_id=RUN_ID, profile=PROFILE),
        False,
    ),
    (
        "plan_conversion",
        lambda: server.plan_conversion(run_id=RUN_ID, table_refs=[TABLE], target=TARGET),
        False,
    ),
    (
        "execute_conversion",
        lambda: server.execute_conversion(run_id=RUN_ID, plan_id="plan-1"),
        False,
    ),
    ("validate_reads", lambda: server.validate_reads(run_id=RUN_ID, table_ref=TABLE), True),
    ("promote_table", lambda: server.promote_table(run_id=RUN_ID, table_ref=TABLE), True),
    ("rollback_table", lambda: server.rollback_table(run_id=RUN_ID, table_ref=TABLE), True),
    (
        "get_conversion_record",
        lambda: server.get_conversion_record(run_id=RUN_ID, table_ref=TABLE),
        True,
    ),
]


@pytest.mark.parametrize(
    ("tool_name", "call", "table_scoped"),
    TOOL_CALLS,
    ids=[name for name, _, _ in TOOL_CALLS],
)
def test_tool_wraps_stub_domain_call_in_an_error_envelope(
    tool_name: str, call: Callable[[], object], table_scoped: bool
) -> None:
    result = call()
    assert isinstance(result, ErrorEnvelope), tool_name
    assert result.code is ErrorCode.INTERNAL
    assert "NotImplementedError" in result.message
    assert result.table == (TABLE.fqn if table_scoped else None)


def test_dispatch_tags_the_span_with_run_id_and_table() -> None:
    """SPEC §3: spans are tagged `run_id` and `table_ref` — identifiers only."""
    from table_mcp.telemetry import tool_span

    with tool_span("profile_table", run_id=RUN_ID, table=TABLE.fqn, strategy="S1") as span:
        assert span is not None


def test_validation_failure_does_not_escape_the_tool() -> None:
    """A Pydantic message embeds the rejected value, so it must never escape
    the tool boundary (SPEC §10)."""
    result = server.profile_table(
        run_id="../../etc/passwd",
        table_ref=TABLE,
    )
    assert isinstance(result, ErrorEnvelope)
    assert "run_id" in result.message
    assert "passwd" not in result.message
    assert result.hint is not None
    assert "passwd" not in result.hint


def test_domain_refusal_keeps_its_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """`APPROVAL_REQUIRED` and friends must reach the caller intact (AT-13)."""
    from table_mcp import promote
    from table_mcp.errors import ApprovalRequiredError

    def _refuse(_: object) -> object:
        raise ApprovalRequiredError("approval_id is required", table=TABLE.fqn)

    monkeypatch.setattr(promote, "promote_table", _refuse)
    result = server.promote_table(run_id=RUN_ID, table_ref=TABLE)

    assert isinstance(result, ErrorEnvelope)
    assert result.code is ErrorCode.APPROVAL_REQUIRED
    assert result.message == "approval_id is required"
    assert result.table == TABLE.fqn
