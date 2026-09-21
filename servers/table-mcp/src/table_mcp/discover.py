"""Unity Catalog discovery (SPEC §3 `discover_tables`, §4).

Read-only. Unity Catalog system tables are read through the minimal auto-stop
serverless SQL warehouse; table data is never read here (zero DBU in the data
path, SPEC §12).

Returns :class:`~table_mcp.schemas.DiscoveredTable` — a frozen `TableRef`
identity plus the discovery attributes — so no other tool can be handed a
half-populated ref (SPEC §14 row 21).

**Non-conforming identifiers are reported, never dropped** (SPEC §14 row 23). A
catalog, schema or table name that fails
:func:`~table_mcp.schemas.is_supported_identifier` cannot be expressed as a
`TableRef`, so it is returned in `DiscoverTablesOutput.unsupported` as an S7
decision with reason `UNSUPPORTED_IDENTIFIER`; `assess-mcp` counts these per
estate so a client exception surfaces at assessment, not at conversion. The raw
name is UC-authored text and is sanitised at the model boundary. Backtick-quoted
identifier support is v1.1.

This module and `profile.py` are the only two permitted to execute Databricks
SQL — enforced by `policies/nowrite.semgrep.yml` and `policies/.importlinter`.
"""

from __future__ import annotations

from table_mcp.schemas import (
    DiscoverTablesInput,
    DiscoverTablesOutput,
    UnsupportedTable,
    is_supported_identifier,
)


def classify_identifier(catalog: str, schema: str, name: str) -> UnsupportedTable | None:
    """Return an `UnsupportedTable` when any part cannot be expressed as a ref.

    Pure and total: it never raises and never drops a table (SPEC §14 row 23).
    """
    bad = [
        field
        for field, value in (("catalog", catalog), ("schema", schema), ("name", name))
        if not is_supported_identifier(value)
    ]
    if not bad:
        return None
    return UnsupportedTable(
        catalog=catalog,
        schema=schema,
        name=name,
        detail=f"non-conforming identifier in: {', '.join(bad)}",
    )


def discover_tables(params: DiscoverTablesInput) -> DiscoverTablesOutput:
    """List in-scope Delta tables with location, size, managed/external, DLT flag."""
    raise NotImplementedError("SPEC §3 discover_tables")
