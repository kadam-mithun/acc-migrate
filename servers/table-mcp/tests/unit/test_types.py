"""Delta → Iceberg type mapping — one named test per SPEC §5 table row.

Server CLAUDE.md: "every type mapping has `test_type_map_<delta_type>`". Each
function below is that named test; the expectation it asserts comes from
`tests/fixtures/expected/types.yaml`, authored by hand from the spec and never
generated from `types.py` (root rule 5).
"""

from __future__ import annotations

from typing import Any

import pytest

from table_mcp.errors import UnmappableDeltaTypeError
from table_mcp.schemas import ManualReason, TimestampMode
from table_mcp.types import iceberg_type_for, map_type, unmappable_reason

from .oracles import load_oracle

ORACLE = load_oracle("types.yaml")


def _assert_mapping(test_name: str) -> None:
    """Assert one oracle entry. The oracle is the source of truth, not this code."""
    case: dict[str, Any] = ORACLE[test_name]
    delta_type = str(case["delta_type"])
    expected = case["expect"]

    if "s7_reason" in expected:
        reason = unmappable_reason(delta_type)
        assert reason is not None, f"{delta_type} must route to rule S7"
        assert reason.value == expected["s7_reason"], test_name
        with pytest.raises(UnmappableDeltaTypeError) as raised:
            map_type(delta_type, column="c")
        assert raised.value.manual_reason.value == expected["s7_reason"]
        return

    mapped = map_type(delta_type, column="c")
    assert mapped.iceberg_type == expected["iceberg_type"], test_name
    assert mapped.type_widened is expected["type_widened"], test_name
    assert mapped.length_constraint_dropped is expected["length_constraint_dropped"], test_name
    assert unmappable_reason(delta_type) is None

    if "expect_ntz_utc" in case:
        ntz = map_type(delta_type, column="c", timestamp_mode=TimestampMode.NTZ_UTC)
        assert ntz.iceberg_type == case["expect_ntz_utc"]["iceberg_type"], test_name


def test_type_map_BYTE() -> None:
    """§5 type table, row BYTE/SHORT/INT"""
    _assert_mapping("test_type_map_BYTE")


def test_type_map_SHORT() -> None:
    """§5 type table, row BYTE/SHORT/INT"""
    _assert_mapping("test_type_map_SHORT")


def test_type_map_INT() -> None:
    """§5 type table, row BYTE/SHORT/INT"""
    _assert_mapping("test_type_map_INT")


def test_type_map_LONG() -> None:
    """§5 type table, row LONG"""
    _assert_mapping("test_type_map_LONG")


def test_type_map_FLOAT() -> None:
    """§5 type table, row FLOAT"""
    _assert_mapping("test_type_map_FLOAT")


def test_type_map_DOUBLE() -> None:
    """§5 type table, row DOUBLE"""
    _assert_mapping("test_type_map_DOUBLE")


def test_type_map_DECIMAL() -> None:
    """§5 type table, row DECIMAL(p,s)"""
    _assert_mapping("test_type_map_DECIMAL")


def test_type_map_BOOLEAN() -> None:
    """§5 type table, row BOOLEAN"""
    _assert_mapping("test_type_map_BOOLEAN")


def test_type_map_STRING() -> None:
    """§5 type table, row STRING/CHAR(n)/VARCHAR(n)"""
    _assert_mapping("test_type_map_STRING")


def test_type_map_CHAR() -> None:
    """§5 type table, row STRING/CHAR(n)/VARCHAR(n) — length constraint dropped"""
    _assert_mapping("test_type_map_CHAR")


def test_type_map_VARCHAR() -> None:
    """§5 type table, row STRING/CHAR(n)/VARCHAR(n) — length constraint dropped"""
    _assert_mapping("test_type_map_VARCHAR")


def test_type_map_BINARY() -> None:
    """§5 type table, row BINARY"""
    _assert_mapping("test_type_map_BINARY")


def test_type_map_DATE() -> None:
    """§5 type table, row DATE"""
    _assert_mapping("test_type_map_DATE")


def test_type_map_TIMESTAMP() -> None:
    """§5 type table, row TIMESTAMP; Gate 0 #18"""
    _assert_mapping("test_type_map_TIMESTAMP")


def test_type_map_TIMESTAMP_NTZ() -> None:
    """§5 type table, row TIMESTAMP_NTZ"""
    _assert_mapping("test_type_map_TIMESTAMP_NTZ")


def test_type_map_ARRAY() -> None:
    """§5 type table, row ARRAY<T> — recursive"""
    _assert_mapping("test_type_map_ARRAY")


def test_type_map_MAP() -> None:
    """§5 type table, row MAP<K,V> — recursive"""
    _assert_mapping("test_type_map_MAP")


def test_type_map_STRUCT() -> None:
    """§5 type table, row STRUCT<...> — recursive"""
    _assert_mapping("test_type_map_STRUCT")


def test_type_map_INTERVAL() -> None:
    """§5 type table, row INTERVAL — no Iceberg equivalent; §14 row 28"""
    _assert_mapping("test_type_map_INTERVAL")


def test_type_map_VARIANT() -> None:
    """§5 type table, row VARIANT — S7 in v1, Iceberg V3 is v1.1"""
    _assert_mapping("test_type_map_VARIANT")


def test_type_map_VOID() -> None:
    """§5 type table, row VOID/NULL — reason void_column"""
    _assert_mapping("test_type_map_VOID")


def test_type_map_NULL() -> None:
    """§5 type table, row VOID/NULL — reason void_column"""
    _assert_mapping("test_type_map_NULL")


def test_type_map_nested_unmappable() -> None:
    """§5 type table, recursive rows combined with the S7 rows"""
    _assert_mapping("test_type_map_nested_unmappable")


def test_oracle_covers_every_row_of_the_spec_table() -> None:
    """A row added to SPEC §5 without an oracle entry must be noticed here."""
    required = {
        "BYTE", "SHORT", "INT", "LONG", "FLOAT", "DOUBLE", "DECIMAL", "BOOLEAN",
        "STRING", "CHAR", "VARCHAR", "BINARY", "DATE", "TIMESTAMP", "TIMESTAMP_NTZ",
        "ARRAY", "MAP", "STRUCT", "INTERVAL", "VARIANT", "VOID", "NULL",
    }  # fmt: skip
    for delta_type in required:
        assert f"test_type_map_{delta_type}" in ORACLE, delta_type
        assert f"test_type_map_{delta_type}" in globals(), f"missing named test for {delta_type}"


def test_type_names_are_case_and_space_insensitive() -> None:
    """Delta schemas render types inconsistently; the mapping must not care."""
    assert map_type("decimal( 18 , 2 )", column="c").iceberg_type == "decimal(18,2)"
    assert map_type("array< int >", column="c").iceberg_type == "list<int>"


def test_struct_round_trips_nested_containers() -> None:
    """SPEC §5 marks the container rows recursive."""
    mapped = iceberg_type_for(
        "STRUCT<id:LONG,tags:ARRAY<STRING>,meta:MAP<STRING,DECIMAL(9,3)>>",
        timestamp_mode=TimestampMode.TIMESTAMPTZ,
    )
    assert mapped == "struct<id:long,tags:list<string>,meta:map<string,decimal(9,3)>>"


def test_nested_unmappable_type_is_reported_from_the_inside() -> None:
    assert unmappable_reason("MAP<STRING,ARRAY<VOID>>") is ManualReason.VOID_COLUMN


def test_unknown_type_is_refused_rather_than_guessed() -> None:
    with pytest.raises(UnmappableDeltaTypeError):
        map_type("GEOGRAPHY", column="c")


def test_malformed_map_is_refused() -> None:
    with pytest.raises(UnmappableDeltaTypeError):
        map_type("MAP<STRING>", column="c")


def test_struct_field_names_keep_their_source_case() -> None:
    """SPEC §8 requires schema equivalence after mapping.

    Case-folding `customerId` to `customerid` would make the mapped nested
    schema non-round-trippable against the source.
    """
    mapped = iceberg_type_for(
        "STRUCT<customerId:STRING,tradeDate:DATE>", timestamp_mode=TimestampMode.TIMESTAMPTZ
    )
    assert mapped == "struct<customerId:string,tradeDate:date>"


def test_interval_with_qualifiers_is_refused() -> None:
    """`INTERVAL DAY TO SECOND` is the spelling Delta emits (§14 row 28)."""
    for spelling in ("INTERVAL", "INTERVAL DAY TO SECOND", "INTERVAL YEAR TO MONTH"):
        assert unmappable_reason(spelling) is ManualReason.UNSUPPORTED_TYPE


def test_unparameterised_decimal_is_refused_not_guessed() -> None:
    """A type the mapper cannot map must never be reported as mappable."""
    assert unmappable_reason("DECIMAL") is ManualReason.UNSUPPORTED_TYPE


def test_struct_field_of_an_unmappable_type_is_reported() -> None:
    """A STRUCT is only as mappable as its fields (SPEC §5 "Recursive")."""
    assert unmappable_reason("STRUCT<id:LONG,payload:VARIANT>") is ManualReason.UNSUPPORTED_TYPE
    assert unmappable_reason("STRUCT<id:LONG,spare:VOID>") is ManualReason.VOID_COLUMN
    assert unmappable_reason("STRUCT<id:LONG,name:STRING>") is None

    with pytest.raises(UnmappableDeltaTypeError):
        map_type("STRUCT<id:LONG,payload:VARIANT>", column="c")


def test_classifier_and_mapper_never_disagree() -> None:
    """The invariant behind rule S7: one parse, one verdict.

    A type the classifier calls mappable but the mapper refuses would route a
    table to zero-copy `add_files` with a column that cannot be written.
    """
    spellings = [
        "INT", "LONG", "STRING", "DECIMAL(9,2)", "CHAR(3)", "TIMESTAMP", "ARRAY<INT>",
        "MAP<STRING,INT>", "STRUCT<a:INT>", "INTERVAL", "INTERVAL DAY TO SECOND", "VARIANT",
        "VOID", "NULL", "GEOGRAPHY", "DECIMAL", "MAP<STRING>", "STRUCT<broken>", "ARRAY<VOID>",
    ]  # fmt: skip
    for spelling in spellings:
        reason = unmappable_reason(spelling)
        if reason is None:
            map_type(spelling, column="c")  # must not raise
        else:
            with pytest.raises(UnmappableDeltaTypeError):
                map_type(spelling, column="c")
