"""Partition handling (SPEC §5, Gate 0 #3/#10).

Identity partitions map directly and keep a table S1/S2 eligible. Generated
partition columns always route to S3 in v1: the equivalent Iceberg transform is
applied, the generated column is dropped from the output schema, and `add_files`
is never attempted (AT-10). Liquid clustering becomes an advisory Iceberg sort
order.

Coverage gate: ≥ 90% on this module.
"""

from __future__ import annotations

from table_mcp.schemas import PartitionColumn, TableProfile


def is_identity_only(profile: TableProfile) -> bool:
    """True when every partition column is an identity partition."""
    raise NotImplementedError("SPEC §5 partitioning")


def iceberg_partition_spec(profile: TableProfile) -> list[PartitionColumn]:
    """Return the Iceberg partition spec, with transforms for generated columns."""
    raise NotImplementedError("SPEC §5 partitioning")


def advisory_sort_order(profile: TableProfile) -> list[str]:
    """Map liquid-clustering / Z-order columns to an advisory Iceberg sort order."""
    raise NotImplementedError("SPEC §5 partitioning")
