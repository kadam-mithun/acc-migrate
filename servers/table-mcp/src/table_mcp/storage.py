"""S3 layout and KMS enforcement (SPEC §10, ADR-0001).

Three-layer KMS enforcement — this module owns layers 1 and 2:

1. the `require_kms_key` precondition, which makes `execute_conversion` refuse
   without `options.kms_key_arn` before any S3 write (AT-15);
2. the config builders that inject the CMK into Spark
   (`fs.s3a.server-side-encryption*`) and PyIceberg FileIO (`s3.sse.*`) at job
   start, so both libraries write SSE-KMS natively.

Layer 3 is the bucket policy in the Terraform module. This module deliberately
does **not** wrap every write (Gate 0 #7).

Staging prefixes are attempt-scoped so a late orphan can never commit into a
newer attempt's location (SPEC §9).
"""

from __future__ import annotations

from table_mcp.schemas import ConversionOptions, ConversionTarget, TableRef


def require_kms_key(options: ConversionOptions) -> str:
    """Return the CMK ARN, or raise `KMS_KEY_REQUIRED` when it is absent."""
    raise NotImplementedError("SPEC §10 KMS enforcement layer 1")


def spark_sse_config(kms_key_arn: str) -> dict[str, str]:
    """`fs.s3a.server-side-encryption*` settings for the EMR Serverless job."""
    raise NotImplementedError("SPEC §10 KMS enforcement layer 2")


def pyiceberg_sse_config(kms_key_arn: str) -> dict[str, str]:
    """`s3.sse.*` settings for PyIceberg FileIO."""
    raise NotImplementedError("SPEC §10 KMS enforcement layer 2")


def staging_location(
    table_ref: TableRef, *, target: ConversionTarget, plan_id: str, attempt: int
) -> str:
    """Deterministic, attempt-scoped staging prefix for a table (SPEC §9)."""
    raise NotImplementedError("SPEC §4 staging layout")


def production_location(table_ref: TableRef, *, target: ConversionTarget) -> str:
    """Production prefix for a promoted table (SPEC §4)."""
    raise NotImplementedError("SPEC §4 production layout")


def delete_staging_prefix(
    table_ref: TableRef, *, target: ConversionTarget, plan_id: str, attempt: int
) -> int:
    """Delete one attempt's staging prefix; returns the object count.

    The prefix is derived here from `(target, table_ref, plan_id, attempt)` rather
    than accepted as a caller-supplied string, so no caller can aim the delete at
    a source location. Implementations recompute it with
    :func:`staging_location` and re-assert :func:`assert_disjoint_from_source`
    before issuing a single delete (SPEC §9, root rule 2).
    """
    raise NotImplementedError("SPEC §9 rollback / recovery cleanup")


def assert_disjoint_from_source(source_locations: list[str], *, target: ConversionTarget) -> None:
    """Hard stop when any staging/production prefix overlaps a source location."""
    raise NotImplementedError("SPEC §9 staging/source disjointness")
