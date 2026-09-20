"""Glue Data Catalog registration (SPEC §7).

Staging and production tables are registered as Iceberg tables
(`table_type = ICEBERG`, `metadata_location` set). UC comments and tags are
carried across as Glue parameters (`uc_tag:{key}`); Lake Formation permissions
are `gov-mcp`'s job and are never applied here.
"""

from __future__ import annotations

from table_mcp.schemas import ConversionTarget, TableRef


def register_iceberg_table(
    table_ref: TableRef,
    *,
    database: str,
    metadata_location: str,
    properties: dict[str, str],
    target: ConversionTarget,
) -> None:
    """Create or update the Glue table entry for a staged/promoted Iceberg table."""
    raise NotImplementedError("SPEC §7 Glue registration")


def drop_staging_table(table_ref: TableRef, *, target: ConversionTarget) -> bool:
    """Drop a **staging** Glue table entry (rollback, stale-RUNNING recovery).

    The database is derived from `target.staging_database_suffix` rather than
    passed in: `rollback_table` is L2 with no human in the loop, so a
    caller-supplied database name could drop a production entry (SPEC §3, §9).
    """
    raise NotImplementedError("SPEC §7 Glue registration")
