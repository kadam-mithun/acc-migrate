"""Conversion execution (SPEC §3 `execute_conversion`, `rollback_table`; §9).

This package holds the per-strategy mechanisms (`s1_snapshot`, `s2_replay`,
`s3_rewrite`, `s4_cdf`, `s6_bridge`) and the orchestration around them:
preconditions, locking, attempt-scoped staging, inline validation, conversion
record, manifest transitions.

Ordering of the four commit points is fixed (SPEC §9): S3 data files → Iceberg
metadata → Glue table → manifest. Nothing earlier is authoritative until the
manifest says `STAGED`, so cleanup is always a staging-prefix delete plus a Glue
table drop.
"""

from __future__ import annotations

from table_mcp.schemas import (
    ExecuteConversionInput,
    ExecuteConversionOutput,
    RollbackTableInput,
    RollbackTableOutput,
    TableProfile,
)

# Ordered commit points; recovery cleans up in reverse (SPEC §9).
COMMIT_ORDER: tuple[str, ...] = ("s3_data_files", "iceberg_metadata", "glue_table", "manifest")


def check_preconditions(profile: TableProfile, *, no_writer_window_minutes: int = 30) -> None:
    """Refuse when the Delta log shows a writer inside the window, when a DLT
    pipeline targeting the table is unpaused, or when the source is a continuous
    streaming table (SPEC §4, AT-06)."""
    raise NotImplementedError("SPEC §4 preconditions")


def execute_conversion(params: ExecuteConversionInput) -> ExecuteConversionOutput:
    """Run a plan (or one table of it) into staging. Idempotent and resumable."""
    raise NotImplementedError("SPEC §3 execute_conversion")


def rollback_table(params: RollbackTableInput) -> RollbackTableOutput:
    """Remove the staged table and its metadata. Never touches source (SPEC §3)."""
    raise NotImplementedError("SPEC §3 rollback_table")
