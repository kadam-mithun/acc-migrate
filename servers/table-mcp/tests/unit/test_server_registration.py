"""`server.py` registers exactly the tools of SPEC §3 and holds no logic."""

from __future__ import annotations

import asyncio

from table_mcp import server

SPEC_TOOLS = {
    "discover_tables",
    "profile_table",
    "recommend_strategy",
    "plan_conversion",
    "execute_conversion",
    "validate_reads",
    "promote_table",
    "rollback_table",
    "get_conversion_record",
}


def test_registered_tools_match_spec_section_3() -> None:
    tools = asyncio.run(server.mcp_server.list_tools())
    assert {tool.name for tool in tools} == SPEC_TOOLS


def test_every_tool_takes_run_id() -> None:
    """SPEC §3: all tools accept `run_id` and tag their span with it."""
    tools = asyncio.run(server.mcp_server.list_tools())
    for tool in tools:
        properties = tool.input_schema.get("properties", {})
        assert "run_id" in properties, tool.name
