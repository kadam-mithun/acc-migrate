"""Partition handling (SPEC §5, Gate 0 #2, AT-10).

Identity partitions map directly and keep a table S1/S2 eligible. Generated
partition columns always route to S3 in v1: the equivalent Iceberg transform is
applied, the generated column is dropped from the output schema, and `add_files`
is never attempted. S1 for transformed partitions is v1.1, pending `add_files`
support for non-identity specs.

Liquid clustering and Z-order become an **advisory** Iceberg sort order on the
same columns, recorded with `SORT_ORDER_ADVISORY`.

Coverage gate: ≥ 90% on this module.
"""

from __future__ import annotations

import re
from typing import Final

from table_mcp.schemas import PartitionColumn, TableProfile

__all__ = [
    "GENERATED_EXPRESSION_TRANSFORMS",
    "advisory_sort_order",
    "iceberg_partition_spec",
    "is_identity_only",
    "output_schema_columns",
    "transform_for_expression",
]

# Delta generated-partition expressions → Iceberg transforms (SPEC §5).
GENERATED_EXPRESSION_TRANSFORMS: Final[dict[str, str]] = {
    "year": "year",
    "month": "month",
    "day": "day",
    "dayofmonth": "day",
    "date": "day",
    "hour": "hour",
}

# `date_trunc('MONTH', ts)` and friends name their unit in the first argument.
_DATE_TRUNC_UNITS: Final[dict[str, str]] = {
    "YEAR": "year",
    "YYYY": "year",
    "MONTH": "month",
    "MM": "month",
    "DAY": "day",
    "DD": "day",
    "DATE": "day",
    "HOUR": "hour",
}

_CALL_RE = re.compile(r"^\s*(\w+)\s*\((.*)\)\s*$", re.DOTALL)
_BUCKET_RE = re.compile(r"^\s*bucket\s*\(\s*(\d+)\s*,", re.IGNORECASE)
_TRUNCATE_RE = re.compile(r"^\s*truncate\s*\(\s*(\d+)\s*,", re.IGNORECASE)


def transform_for_expression(expression: str) -> str | None:
    """Map a Delta generated-column expression to an Iceberg transform name.

    Returns None when the expression has no equivalent transform, which keeps
    the table on S3 with the partition column rewritten rather than translated.
    """
    if bucket := _BUCKET_RE.match(expression):
        return f"bucket[{bucket.group(1)}]"
    if truncate := _TRUNCATE_RE.match(expression):
        return f"truncate[{truncate.group(1)}]"

    call = _CALL_RE.match(expression)
    if call is None:
        return None
    function = call.group(1).lower()

    if function == "date_trunc":
        arguments = call.group(2).split(",")
        unit = arguments[0].strip().strip("'\"").upper() if arguments else ""
        return _DATE_TRUNC_UNITS.get(unit)

    return GENERATED_EXPRESSION_TRANSFORMS.get(function)


def is_identity_only(profile: TableProfile) -> bool:
    """True when every partition column is an identity partition (S1/S2 eligible).

    An unpartitioned table is identity-only: there is nothing to transform.
    """
    return all(column.identity for column in profile.partition_columns)


def iceberg_partition_spec(profile: TableProfile) -> list[PartitionColumn]:
    """Return the Iceberg partition spec, with transforms for generated columns.

    Identity partitions keep the `identity` transform. A generated partition
    column is replaced by the transform over its source column, so the generated
    column itself does not appear in the output schema (AT-10).
    """
    spec: list[PartitionColumn] = []
    for column in profile.partition_columns:
        if column.identity:
            spec.append(
                PartitionColumn(
                    name=column.name,
                    identity=True,
                    source_column=column.source_column or column.name,
                    iceberg_transform="identity",
                )
            )
            continue

        transform = column.iceberg_transform
        if transform is None and column.generated_expression is not None:
            transform = transform_for_expression(column.generated_expression)
        spec.append(
            PartitionColumn(
                name=column.name,
                identity=False,
                source_column=column.source_column,
                generated_expression=column.generated_expression,
                iceberg_transform=transform,
            )
        )
    return spec


def output_schema_columns(profile: TableProfile) -> list[str]:
    """Column names of the converted table.

    Generated partition columns are dropped: the Iceberg transform reproduces
    them from the source column, so keeping both would duplicate the value
    (SPEC §5, AT-10).
    """
    generated = {
        column.name
        for column in profile.partition_columns
        if not column.identity and column.generated_expression is not None
    }
    return [column.name for column in profile.columns if column.name not in generated]


def advisory_sort_order(profile: TableProfile) -> list[str]:
    """Map liquid-clustering / Z-order columns to an advisory Iceberg sort order.

    Advisory only: Iceberg's sort order is a write-time hint, not the clustering
    guarantee Delta gives, so the difference is documented in the record and
    flagged with `SORT_ORDER_ADVISORY`.
    """
    if not profile.features.liquid_clustering:
        return []
    return list(profile.features.clustering_columns)
