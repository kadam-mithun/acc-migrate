"""Validation (SPEC §8).

Two layers:

* inline validation run by `execute_conversion` before a table is marked
  `STAGED` — exact row count, schema equivalence, column aggregates on up to 20
  deterministically selected columns, partition count and distribution;
* `validate_reads`, which must get agreement from Athena, Redshift (native
  Glue-mounted Iceberg read, Spectrum fallback) and EMR Spark.

Aggregate *values* go only to the encrypted conversion record; logs carry the
match/mismatch flag and a hash of the aggregate vector (SPEC §8, §10).
"""

from __future__ import annotations

from table_mcp.schemas import (
    ColumnAggregate,
    TableProfile,
    ValidateReadsInput,
    ValidateReadsOutput,
    ValidationResult,
)


def select_checksum_columns(profile: TableProfile, *, limit: int = 20) -> list[str]:
    """Deterministic selection: partition columns, then primary/unique-key columns
    from Delta constraints, then remaining columns in schema order (SPEC §8)."""
    raise NotImplementedError("SPEC §8 checksum column selection")


def validate_staged_table(
    profile: TableProfile,
    *,
    staged_metadata_location: str,
    float_tolerance: float = 1e-9,
) -> tuple[ValidationResult, list[ColumnAggregate]]:
    """Run the inline validation. Returns the loggable result and the aggregate
    values, which the caller writes only to the encrypted conversion record."""
    raise NotImplementedError("SPEC §8 inline validation")


def validate_reads(params: ValidateReadsInput) -> ValidateReadsOutput:
    """Confirm the staged table reads identically from all three engines."""
    raise NotImplementedError("SPEC §8 validate_reads")
