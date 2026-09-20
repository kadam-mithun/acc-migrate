"""Unity Catalog discovery (SPEC §3 `discover_tables`, §4).

Read-only. Unity Catalog system tables are read through the minimal auto-stop
serverless SQL warehouse; table data is never read here (zero DBU in the data
path, SPEC §12).
"""

from __future__ import annotations

from table_mcp.schemas import DiscoverTablesInput, DiscoverTablesOutput


def discover_tables(params: DiscoverTablesInput) -> DiscoverTablesOutput:
    """List in-scope Delta tables with location, size, managed/external, DLT flag."""
    raise NotImplementedError("SPEC §3 discover_tables")
