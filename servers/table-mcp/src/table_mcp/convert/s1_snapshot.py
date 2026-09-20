"""S1 — metadata-only snapshot (SPEC §5).

Registers existing Parquet files as an Iceberg table with a single snapshot via
PyIceberg `add_files`. Zero data copy. Eligible only for identity partitions and
files untouched by Delta features; a `name`-mode column mapping is carried as an
Iceberg name mapping (`schema.name-mapping.default`) generated from the Delta
schema metadata. Prior versions are recorded as metadata in the conversion
record, not as Iceberg snapshots.
"""

from __future__ import annotations

from table_mcp.schemas import ConversionOptions, ConversionTarget, TableProfile


def convert(
    profile: TableProfile, *, options: ConversionOptions, target: ConversionTarget, staging: str
) -> str:
    """Register the Iceberg table and return its metadata location."""
    raise NotImplementedError("SPEC §5 S1 metadata-only snapshot")
