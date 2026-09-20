"""Run manifest and evidence ledger (SPEC §9, §10).

Two stores:

* the DynamoDB run manifest `acc_migrate_runs`, holding `run_id, plan_id,
  table_ref, state, attempt, strategy, heartbeat_at, lease_expires_at,
  emr_application_id, emr_job_run_id, staged_snapshot_id,
  staged_metadata_location, last_error (redacted), record_pointer`;
* the conversion record, one JSON per table, written SSE-KMS encrypted to
  `s3://{bucket}/acc-migrate/evidence/{run_id}/{table}.json`.

Records carry counts, hashes, paths and — in the encrypted record only —
column aggregates. Never data values anywhere else (root rule 4).
"""

from __future__ import annotations

from datetime import datetime

from table_mcp.schemas import (
    ApprovalRecord,
    ConversionRecord,
    ConversionTarget,
    ErrorEnvelope,
    GetConversionRecordInput,
    GetConversionRecordOutput,
    TableRef,
    TableState,
)


def put_manifest_state(
    *,
    run_id: str,
    plan_id: str,
    table_ref: TableRef,
    state: TableState,
    attempt: int,
    target: ConversionTarget,
    last_error: ErrorEnvelope | None = None,
) -> None:
    """Write the table's state to the run manifest."""
    raise NotImplementedError("SPEC §9 run manifest")


def heartbeat(*, run_id: str, table_ref: TableRef, target: ConversionTarget) -> datetime:
    """Refresh `heartbeat_at` and the lease (every 60 s while RUNNING, SPEC §9)."""
    raise NotImplementedError("SPEC §9 run manifest")


def write_conversion_record(
    record: ConversionRecord, *, target: ConversionTarget, kms_key_arn: str
) -> str:
    """Write the evidence record and return its S3 URI (`record_pointer`).

    The CMK is a required argument, not an ambient default: this object is the
    only artefact permitted to hold column aggregates, so SPEC §10 requires it
    SSE-KMS encrypted. Implementations route the ARN through
    `storage.require_kms_key` and must never fall back to SSE-S3.
    """
    raise NotImplementedError("SPEC §10 evidence record")


def get_conversion_record(params: GetConversionRecordInput) -> GetConversionRecordOutput:
    """Return the evidence record for a table (SPEC §3)."""
    raise NotImplementedError("SPEC §3 get_conversion_record")


def get_approval_record(approval_id: str, *, target: ConversionTarget) -> ApprovalRecord | None:
    """Fetch the approval record, or None when the id is unknown (SPEC §9.1)."""
    raise NotImplementedError("SPEC §9.1 approval lookup")
