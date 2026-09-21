"""MCP tool registration for `table-mcp`.

**Registration only — no logic here** (SPEC §13). Each tool validates its input
with the Pydantic model from `schemas.py`, opens the OpenTelemetry span tagged
with `run_id` and `table_ref`, delegates to exactly one domain function, and
returns either that function's typed output or a redacted `ErrorEnvelope`
(SPEC §3, §10).

Transport: streamable HTTP via AgentCore Gateway; also runnable locally over
stdio for Claude Code.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from pydantic import ValidationError

from table_mcp import convert, discover, ledger, profile, promote, strategy, validate
from table_mcp.errors import TableMcpError
from table_mcp.redact import (
    configure_logging,
    domain_error_envelope,
    to_error_envelope,
    validation_error_envelope,
)
from table_mcp.schemas import (
    ConversionOptions,
    ConversionTarget,
    DiscoverTablesInput,
    DiscoverTablesOutput,
    ErrorEnvelope,
    ExecuteConversionInput,
    ExecuteConversionOutput,
    GetConversionRecordInput,
    GetConversionRecordOutput,
    PlanConversionInput,
    PlanConversionOutput,
    ProfileTableInput,
    ProfileTableOutput,
    PromoteTableInput,
    PromoteTableOutput,
    RecommendStrategyInput,
    RecommendStrategyOutput,
    RollbackTableInput,
    RollbackTableOutput,
    TableProfile,
    TableRef,
    ToolInput,
    ValidateReadsInput,
    ValidateReadsOutput,
)
from table_mcp.telemetry import tool_span

mcp_server = MCPServer("table-mcp")


def _table_fqn(fields: dict[str, Any]) -> str | None:
    """Span/error tag for table-scoped calls; identity only, never a data value.

    Read from the raw arguments rather than the validated model, because the tag
    is needed even when validation is what failed.
    """
    ref = fields.get("table_ref")
    return ref.fqn if isinstance(ref, TableRef) else None


def _dispatch[TIn: ToolInput, TOut](
    tool: str,
    model: type[TIn],
    handler: Callable[[TIn], TOut],
    fields: dict[str, Any],
) -> TOut | ErrorEnvelope:
    """Validate, span, delegate, wrap. The only shared code path in this module.

    Input validation happens **inside** the guarded block: a Pydantic
    `ValidationError` carries the rejected value in its message, so letting one
    escape the tool would put a data value in the caller's error path. It is
    converted to a field-names-only envelope instead (SPEC §10).
    """
    raw_run_id = fields.get("run_id")
    run_id = raw_run_id if isinstance(raw_run_id, str) else ""
    table = _table_fqn(fields)
    with tool_span(tool, run_id=run_id, table=table):
        try:
            params = model.model_validate(fields)
        except ValidationError as exc:
            return validation_error_envelope(exc, table=table)
        try:
            return handler(params)
        # A refusal that already knows its ErrorCode keeps it (SPEC §3).
        except TableMcpError as exc:
            return domain_error_envelope(exc)
        # SPEC §3/§10: every other library exception becomes a structured,
        # scrubbed ErrorEnvelope. Catching broadly is the requirement here.
        except Exception as exc:  # noqa: BLE001
            return to_error_envelope(exc, table=table)


@mcp_server.tool()
def discover_tables(
    run_id: str,
    catalog: str,
    schema: str | None = None,
    filter: str | None = None,
) -> DiscoverTablesOutput | ErrorEnvelope:
    """List Delta tables in scope via Unity Catalog system tables. Read-only."""
    return _dispatch(
        "discover_tables",
        DiscoverTablesInput,
        discover.discover_tables,
        {"run_id": run_id, "catalog": catalog, "schema": schema, "filter": filter},
    )


@mcp_server.tool()
def profile_table(run_id: str, table_ref: TableRef) -> ProfileTableOutput | ErrorEnvelope:
    """Deep inspection of the Delta log for one table. Read-only."""
    return _dispatch(
        "profile_table",
        ProfileTableInput,
        profile.profile_table,
        {"run_id": run_id, "table_ref": table_ref},
    )


@mcp_server.tool()
def recommend_strategy(
    run_id: str,
    profile: TableProfile,
    options: ConversionOptions | None = None,
) -> RecommendStrategyOutput | ErrorEnvelope:
    """Return the `StrategyDecision` for a profile (SPEC §5). Pure function."""
    return _dispatch(
        "recommend_strategy",
        RecommendStrategyInput,
        strategy.recommend_strategy,
        {"run_id": run_id, "profile": profile, "options": options or ConversionOptions()},
    )


@mcp_server.tool()
def plan_conversion(
    run_id: str,
    table_refs: list[TableRef],
    target: ConversionTarget,
    options: ConversionOptions | None = None,
) -> PlanConversionOutput | ErrorEnvelope:
    """Produce a `ConversionPlan`. Pure function; no side effects."""
    return _dispatch(
        "plan_conversion",
        PlanConversionInput,
        strategy.plan_conversion,
        {
            "run_id": run_id,
            "table_refs": table_refs,
            "target": target,
            "options": options or ConversionOptions(),
        },
    )


@mcp_server.tool()
def execute_conversion(
    run_id: str,
    plan_id: str,
    table_ref: TableRef | None = None,
    force: bool = False,
) -> ExecuteConversionOutput | ErrorEnvelope:
    """Run the plan (or one table of it) into staging. L2 — staging only."""
    return _dispatch(
        "execute_conversion",
        ExecuteConversionInput,
        convert.execute_conversion,
        {"run_id": run_id, "plan_id": plan_id, "table_ref": table_ref, "force": force},
    )


@mcp_server.tool()
def validate_reads(run_id: str, table_ref: TableRef) -> ValidateReadsOutput | ErrorEnvelope:
    """Confirm the staged table reads from Athena, Redshift and EMR Spark."""
    return _dispatch(
        "validate_reads",
        ValidateReadsInput,
        validate.validate_reads,
        {"run_id": run_id, "table_ref": table_ref},
    )


@mcp_server.tool()
def promote_table(
    run_id: str,
    table_ref: TableRef,
    approval_id: str | None = None,
) -> PromoteTableOutput | ErrorEnvelope:
    """Move a staged table to production. L1 — human approval required (SPEC §9.1)."""
    return _dispatch(
        "promote_table",
        PromoteTableInput,
        promote.promote_table,
        {"run_id": run_id, "table_ref": table_ref, "approval_id": approval_id},
    )


@mcp_server.tool()
def rollback_table(run_id: str, table_ref: TableRef) -> RollbackTableOutput | ErrorEnvelope:
    """Remove the staged table and its metadata. Never touches source. L2."""
    return _dispatch(
        "rollback_table",
        RollbackTableInput,
        convert.rollback_table,
        {"run_id": run_id, "table_ref": table_ref},
    )


@mcp_server.tool()
def get_conversion_record(
    run_id: str, table_ref: TableRef
) -> GetConversionRecordOutput | ErrorEnvelope:
    """Return the evidence record for a table. Read-only."""
    return _dispatch(
        "get_conversion_record",
        GetConversionRecordInput,
        ledger.get_conversion_record,
        {"run_id": run_id, "table_ref": table_ref},
    )


def main() -> None:
    """Run over stdio for local Claude Code use.

    In the client account the server is reached over streamable HTTP through the
    AgentCore Gateway (SPEC §3).
    """
    configure_logging()
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()
