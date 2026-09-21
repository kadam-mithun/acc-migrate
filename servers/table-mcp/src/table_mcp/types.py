"""Delta → Iceberg type mapping (SPEC §5, exhaustive table).

Every row of the spec table has a named test `test_type_map_<delta_type>`, and
the expected results are authored in `tests/fixtures/expected/types.yaml` from
the spec, never generated from this code (root rule 5).

Three Delta types have no Iceberg equivalent in v1 and route to rule S7:
`INTERVAL` and `VARIANT` with reason `unsupported_type`, `VOID`/`NULL` with
reason `void_column` (SPEC §5, §14 rows 26/28).

**One parse, one verdict.** :func:`iceberg_type_for` is the only place a Delta
type is interpreted, and :func:`unmappable_reason` is defined in terms of it.
They cannot disagree, which matters because `strategy.rule_s7` decides S7 from
`unmappable_reason`: a type the mapper cannot map but the classifier called
mappable would send a table to zero-copy `add_files` with a column that cannot
be written. Anything unrecognised is therefore refused, not assumed mappable —
`INTERVAL DAY TO SECOND` and `DECIMAL` without parameters included.

Coverage gate: ≥ 90% on this module.
"""

from __future__ import annotations

import re
from typing import Final

from table_mcp.errors import UnmappableDeltaTypeError
from table_mcp.schemas import ManualReason, TimestampMode, TypeMappingRecord

__all__ = [
    "SCALAR_TYPES",
    "UNMAPPABLE_TYPES",
    "iceberg_type_for",
    "map_type",
    "unmappable_reason",
]

# Delta types with no Iceberg equivalent in v1 → rule S7 (SPEC §5, Gate 0 #4).
UNMAPPABLE_TYPES: Final[dict[str, ManualReason]] = {
    "INTERVAL": ManualReason.UNSUPPORTED_TYPE,
    "VARIANT": ManualReason.UNSUPPORTED_TYPE,
    "VOID": ManualReason.VOID_COLUMN,
    "NULL": ManualReason.VOID_COLUMN,
}

# The parameterless rows of the SPEC §5 table.
SCALAR_TYPES: Final[dict[str, str]] = {
    "BYTE": "int",
    "SHORT": "int",
    "INT": "int",
    "LONG": "long",
    "FLOAT": "float",
    "DOUBLE": "double",
    "BOOLEAN": "boolean",
    "STRING": "string",
    "BINARY": "binary",
    "DATE": "date",
    "TIMESTAMP_NTZ": "timestamp",
}

# BYTE and SHORT widen to `int`; recorded as `type_widened` in the record.
_WIDENED_TO_INT: Final[frozenset[str]] = frozenset({"BYTE", "SHORT"})

_DECIMAL_RE = re.compile(r"^DECIMAL\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$", re.IGNORECASE)
_CHAR_RE = re.compile(r"^(?:CHAR|VARCHAR)\s*\(\s*(\d+)\s*\)$", re.IGNORECASE)
_ARRAY_RE = re.compile(r"^ARRAY\s*<(.+)>$", re.IGNORECASE | re.DOTALL)
_MAP_RE = re.compile(r"^MAP\s*<(.+)>$", re.IGNORECASE | re.DOTALL)
_STRUCT_RE = re.compile(r"^STRUCT\s*<(.*)>$", re.IGNORECASE | re.DOTALL)


def _normalise(delta_type: str) -> str:
    """Collapse whitespace, preserving case so STRUCT field names survive."""
    return re.sub(r"\s+", " ", delta_type.strip())


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not inside angle brackets or parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "<(":
            depth += 1
        elif char in ">)":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _base_name(normalised: str) -> str:
    """The leading type name, without parameters or element types."""
    return normalised.split("(")[0].split("<")[0].strip().upper()


def iceberg_type_for(delta_type: str, *, timestamp_mode: TimestampMode) -> str:
    """Return the Iceberg type name for one Delta type (SPEC §5).

    The single point of interpretation: every caller, including
    :func:`unmappable_reason`, goes through here.

    Raises:
        UnmappableDeltaTypeError: the type routes to rule S7, carrying the
            precise `ManualReason` (`unsupported_type` or `void_column`).
    """
    normalised = _normalise(delta_type)
    upper = normalised.upper()
    base = _base_name(normalised)

    if base in UNMAPPABLE_TYPES:
        raise UnmappableDeltaTypeError(
            f"Delta type {base} has no Iceberg equivalent in v1",
            manual_reason=UNMAPPABLE_TYPES[base],
        )

    # `INTERVAL DAY TO SECOND`, `INTERVAL YEAR TO MONTH` — the spellings Delta
    # actually emits. The bare word is caught above; these are not.
    if upper.startswith("INTERVAL"):
        raise UnmappableDeltaTypeError(
            "Delta INTERVAL types have no Iceberg equivalent in v1",
            manual_reason=ManualReason.UNSUPPORTED_TYPE,
        )

    if upper in SCALAR_TYPES:
        return SCALAR_TYPES[upper]

    if upper == "TIMESTAMP":
        # Delta TIMESTAMP has instant semantics, so timestamptz is faithful.
        # ntz_utc normalises to UTC instead and forces S3 (Gate 0 #18).
        return "timestamp" if timestamp_mode is TimestampMode.NTZ_UTC else "timestamptz"

    if decimal := _DECIMAL_RE.match(normalised):
        precision, scale = decimal.groups()
        return f"decimal({precision},{scale})"

    if _CHAR_RE.match(normalised):
        return "string"

    if array := _ARRAY_RE.match(normalised):
        element = iceberg_type_for(array.group(1), timestamp_mode=timestamp_mode)
        return f"list<{element}>"

    if mapping := _MAP_RE.match(normalised):
        parts = _split_top_level(mapping.group(1))
        if len(parts) != 2:
            raise UnmappableDeltaTypeError(
                "MAP requires exactly a key type and a value type",
                manual_reason=ManualReason.UNSUPPORTED_TYPE,
            )
        key = iceberg_type_for(parts[0], timestamp_mode=timestamp_mode)
        value = iceberg_type_for(parts[1], timestamp_mode=timestamp_mode)
        return f"map<{key},{value}>"

    if struct := _STRUCT_RE.match(normalised):
        fields: list[str] = []
        for field in _split_top_level(struct.group(1)):
            name, separator, field_type = field.partition(":")
            if not separator:
                raise UnmappableDeltaTypeError(
                    "STRUCT fields must be written name:type",
                    manual_reason=ManualReason.UNSUPPORTED_TYPE,
                )
            mapped = iceberg_type_for(field_type, timestamp_mode=timestamp_mode)
            # Field names keep their source case: SPEC §8 requires schema
            # equivalence after mapping, which case folding would break.
            fields.append(f"{name.strip()}:{mapped}")
        return f"struct<{','.join(fields)}>"

    raise UnmappableDeltaTypeError(
        f"unrecognised Delta type {base}",
        manual_reason=ManualReason.UNSUPPORTED_TYPE,
    )


def unmappable_reason(delta_type: str) -> ManualReason | None:
    """Return the S7 reason for a type that cannot be mapped, else None.

    Defined in terms of :func:`iceberg_type_for` so the classifier and the
    mapper can never disagree. Recurses by construction, so `ARRAY<VARIANT>`
    and `STRUCT<a:VOID>` are reported too.
    """
    try:
        iceberg_type_for(delta_type, timestamp_mode=TimestampMode.TIMESTAMPTZ)
    except UnmappableDeltaTypeError as exc:
        return exc.manual_reason
    return None


def map_type(
    delta_type: str,
    *,
    column: str,
    timestamp_mode: TimestampMode = TimestampMode.TIMESTAMPTZ,
) -> TypeMappingRecord:
    """Map one Delta column type, recording widening and dropped length constraints.

    Raises:
        UnmappableDeltaTypeError: the type routes to rule S7.
    """
    normalised = _normalise(delta_type)
    return TypeMappingRecord(
        column=column,
        delta_type=normalised.upper(),
        iceberg_type=iceberg_type_for(normalised, timestamp_mode=timestamp_mode),
        type_widened=normalised.upper() in _WIDENED_TO_INT,
        length_constraint_dropped=_CHAR_RE.match(normalised) is not None,
    )
