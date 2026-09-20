"""Delta log inspection (SPEC §3 `profile_table`).

Reads the Delta log directly from S3 via delta-rs / Delta Kernel — protocol
versions, table features, partition scheme, schema history, version ledger,
active file count and tombstones. Read-only; no Databricks compute.
"""

from __future__ import annotations

from table_mcp.schemas import ProfileTableInput, ProfileTableOutput


def profile_table(params: ProfileTableInput) -> ProfileTableOutput:
    """Build the `TableProfile` that drives the strategy matrix."""
    raise NotImplementedError("SPEC §3 profile_table")
