"""Delta → Iceberg type mapping (SPEC §5, exhaustive table).

Every row of the spec table has a named test `test_type_map_<delta_type>`, and
the human-authored oracle lives in `tests/fixtures/expected/types.yaml`.
`INTERVAL`, `VARIANT` and `VOID`/`NULL` have no v1 mapping and route to S7.

Coverage gate: ≥ 90% on this module.
"""

from __future__ import annotations

from table_mcp.schemas import TimestampMode, TypeMappingRecord

# Delta types with no Iceberg equivalent in v1 → rule S7 (SPEC §5, Gate 0 #4).
UNMAPPABLE_TYPES: frozenset[str] = frozenset({"INTERVAL", "VARIANT", "VOID", "NULL"})


def map_type(
    delta_type: str,
    *,
    column: str,
    timestamp_mode: TimestampMode = TimestampMode.TIMESTAMPTZ,
) -> TypeMappingRecord:
    """Map one Delta type to its Iceberg type, recording widening and dropped
    length constraints. Raises for a type in :data:`UNMAPPABLE_TYPES`."""
    raise NotImplementedError("SPEC §5 type mapping")
