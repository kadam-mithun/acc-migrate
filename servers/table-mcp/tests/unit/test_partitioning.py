"""Partition handling (SPEC §5 partitioning paragraph, AT-10).

Identity partitions keep a table S1/S2-eligible; generated partition columns
route to S3, where the equivalent Iceberg transform is applied and the generated
column is dropped from the output schema. Liquid clustering becomes an advisory
sort order.
"""

from __future__ import annotations

import pytest

from table_mcp.partitioning import (
    advisory_sort_order,
    iceberg_partition_spec,
    is_identity_only,
    output_schema_columns,
    transform_for_expression,
)

from .oracles import build_profile


def test_identity_partitions_keep_a_table_metadata_eligible() -> None:
    """SPEC §5: identity partitions map directly, so S1/S2 stay available."""
    profile = build_profile({})
    assert is_identity_only(profile)
    spec = iceberg_partition_spec(profile)
    assert [column.iceberg_transform for column in spec] == ["identity"]


def test_unpartitioned_table_is_identity_only() -> None:
    """Nothing to transform, so nothing blocks add_files."""
    profile = build_profile({"partition_columns": []})
    profile = profile.model_copy(update={"partition_columns": []})
    assert is_identity_only(profile)
    assert iceberg_partition_spec(profile) == []


def test_generated_partition_is_not_identity_only() -> None:
    """SPEC §5: any non-identity partition scheme routes to S3."""
    profile = build_profile(
        {
            "partition_columns": [
                {"name": "event_year", "identity": False, "generated_expression": "year(ts)"}
            ]
        }
    )
    assert not is_identity_only(profile)


def test_generated_partition_uses_the_iceberg_transform() -> None:
    """AT-10: the partition spec uses the transform, not the generated column."""
    profile = build_profile(
        {
            "partition_columns": [
                {
                    "name": "event_year",
                    "identity": False,
                    "source_column": "ts",
                    "generated_expression": "year(ts)",
                }
            ]
        }
    )
    spec = iceberg_partition_spec(profile)
    assert [column.iceberg_transform for column in spec] == ["year"]
    assert spec[0].source_column == "ts"


def test_generated_partition_column_is_dropped_from_the_output_schema() -> None:
    """AT-10: no generated column in the output schema."""
    profile = build_profile(
        {
            "columns": [
                {"name": "ts", "type": "TIMESTAMP"},
                {"name": "event_year", "type": "INT"},
                {"name": "notional", "type": "DECIMAL(18,2)"},
            ],
            "partition_columns": [
                {
                    "name": "event_year",
                    "identity": False,
                    "source_column": "ts",
                    "generated_expression": "year(ts)",
                }
            ],
        }
    )
    assert output_schema_columns(profile) == ["ts", "notional"]


def test_identity_partition_column_stays_in_the_output_schema() -> None:
    profile = build_profile(
        {
            "columns": [{"name": "trade_date", "type": "DATE"}],
            "partition_columns": [{"name": "trade_date", "identity": True}],
        }
    )
    assert output_schema_columns(profile) == ["trade_date"]


@pytest.mark.parametrize(
    ("expression", "transform"),
    [
        ("year(ts)", "year"),
        ("month(ts)", "month"),
        ("day(ts)", "day"),
        ("dayofmonth(ts)", "day"),
        ("hour(ts)", "hour"),
        ("date(ts)", "day"),
        ("date_trunc('MONTH', ts)", "month"),
        ("date_trunc('YEAR', ts)", "year"),
        ("date_trunc('DAY', ts)", "day"),
        ("bucket(16, customer_id)", "bucket[16]"),
        ("truncate(8, postcode)", "truncate[8]"),
    ],
)
def test_generated_expressions_map_to_iceberg_transforms(expression: str, transform: str) -> None:
    """SPEC §5: "the equivalent Iceberg transform, e.g. year(ts)"."""
    assert transform_for_expression(expression) == transform


@pytest.mark.parametrize(
    "expression",
    ["substring(code, 1, 3)", "concat(a, b)", "not_a_call", "date_trunc('DECADE', ts)"],
)
def test_expressions_without_an_equivalent_transform_return_none(expression: str) -> None:
    """No equivalent transform means the column is rewritten, not translated."""
    assert transform_for_expression(expression) is None


def test_partition_spec_records_an_untranslatable_expression() -> None:
    """The spec entry still carries the expression, so the record can explain it."""
    profile = build_profile(
        {
            "partition_columns": [
                {
                    "name": "prefix",
                    "identity": False,
                    "generated_expression": "substring(code, 1, 3)",
                }
            ]
        }
    )
    spec = iceberg_partition_spec(profile)
    assert spec[0].iceberg_transform is None
    assert spec[0].generated_expression == "substring(code, 1, 3)"


def test_liquid_clustering_becomes_an_advisory_sort_order() -> None:
    """SPEC §5: liquid clustering → Iceberg sort order on the same columns."""
    profile = build_profile(
        {"liquid_clustering": True, "clustering_columns": ["trade_date", "book"]}
    )
    assert advisory_sort_order(profile) == ["trade_date", "book"]


def test_no_clustering_means_no_sort_order() -> None:
    assert advisory_sort_order(build_profile({})) == []
