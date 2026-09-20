"""OpenTelemetry spans for tool calls and strategy steps (SPEC §10).

Every tool call opens a span tagged with `run_id`, `table_ref` and `strategy`
(SPEC §3). Tags carry identifiers only — never column or partition values.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace

_TRACER = trace.get_tracer("table-mcp")


@contextmanager
def tool_span(
    tool: str,
    *,
    run_id: str,
    table: str | None = None,
    strategy: str | None = None,
) -> Iterator[trace.Span]:
    """Open the span for one tool call.

    Args:
        tool: MCP tool name, used as the span name.
        run_id: Correlates every span of a run.
        table: Fully-qualified table name, when the call is table-scoped.
        strategy: Strategy id, when already decided.
    """
    with _TRACER.start_as_current_span(f"table-mcp.{tool}") as span:
        span.set_attribute("run_id", run_id)
        if table is not None:
            span.set_attribute("table_ref", table)
        if strategy is not None:
            span.set_attribute("strategy", strategy)
        yield span
