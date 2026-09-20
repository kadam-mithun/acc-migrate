"""Per-table locking and stale-RUNNING recovery (SPEC §9).

A DynamoDB conditional write takes a lease (default TTL 30 min) refreshed by the
worker heartbeat; a crashed worker's lock expires. A second concurrent run is
refused with `LOCKED` (AT-12).

Recovery order for a stale `RUNNING` table is strict and must not be reordered
(AT-17, AT-19): cancel the EMR job run first and wait for a terminal state
(timeout 10 min → `RECOVERY_BLOCKED`), then drop the staging Glue table, then
delete the attempt's staging prefix, then restart.
"""

from __future__ import annotations

from table_mcp.schemas import ConversionTarget, TableRef

RECOVERY_ORDER: tuple[str, ...] = (
    "cancel_emr_job_run",
    "drop_staging_glue_table",
    "delete_attempt_prefix",
    "restart",
)


def acquire(
    *, run_id: str, table_ref: TableRef, target: ConversionTarget, lease_ttl_minutes: int = 30
) -> bool:
    """Take the per-table lease. False when another run holds a live lease."""
    raise NotImplementedError("SPEC §9 per-table lock")


def release(*, run_id: str, table_ref: TableRef, target: ConversionTarget) -> None:
    """Release the lease held by this run."""
    raise NotImplementedError("SPEC §9 per-table lock")


def recover_stale_running(*, run_id: str, table_ref: TableRef, target: ConversionTarget) -> None:
    """Run :data:`RECOVERY_ORDER` for a table whose heartbeat is past the lease TTL."""
    raise NotImplementedError("SPEC §9 stale RUNNING recovery")
