"""The human-authored oracles that drive the strategy and type unit tests.

SPEC §11 / Gate 0 #9: expected strategy and type decisions are human-authored
from the SPEC §5 tables and live in `tests/fixtures/expected/strategy.yaml` and
`types.yaml`. Root rule 5 forbids generating them from the code under test.

These tests guard the oracle files themselves. The per-rule tests
(`test_strategy_rule_<id>`, `test_type_map_<delta_type>`) are added alongside
`strategy.py` and `types.py` and read their expectations from here; they cannot
be written against an empty oracle, so this module reports that state loudly
rather than passing silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

EXPECTED_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "expected"
STRATEGY_ORACLE = EXPECTED_DIR / "strategy.yaml"
TYPES_ORACLE = EXPECTED_DIR / "types.yaml"


def _load(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


@pytest.mark.parametrize("path", [STRATEGY_ORACLE, TYPES_ORACLE])
def test_oracle_file_exists_and_parses(path: Path) -> None:
    assert path.is_file(), f"{path.name} is missing"
    yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", [STRATEGY_ORACLE, TYPES_ORACLE])
def test_oracle_explains_who_fills_it_in(path: Path) -> None:
    header = path.read_text(encoding="utf-8")
    assert "WHO FILLS THIS IN" in header
    assert "lead architect" in header


@pytest.mark.skipif(
    not _load(STRATEGY_ORACLE),
    reason="strategy.yaml is empty — a human authors it from SPEC §5 (root rule 5)",
)
def test_strategy_oracle_covers_every_rule() -> None:
    """Every rule id in the SPEC §5 decision order has at least one entry."""
    entries = _load(STRATEGY_ORACLE)
    for rule_id in ("S1", "S2", "S3", "S4", "S5", "S6", "S7"):
        assert f"test_strategy_rule_{rule_id}" in entries, rule_id


@pytest.mark.skipif(
    not _load(TYPES_ORACLE),
    reason="types.yaml is empty — a human authors it from the SPEC §5 type table",
)
def test_type_oracle_covers_every_row_of_the_spec_table() -> None:
    """Every Delta type in the SPEC §5 table has a `test_type_map_<type>` entry."""
    entries = _load(TYPES_ORACLE)
    delta_types = (
        "BYTE",
        "SHORT",
        "INT",
        "LONG",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
        "BOOLEAN",
        "STRING",
        "CHAR",
        "VARCHAR",
        "BINARY",
        "DATE",
        "TIMESTAMP",
        "TIMESTAMP_NTZ",
        "ARRAY",
        "MAP",
        "STRUCT",
        "INTERVAL",
        "VARIANT",
        "VOID",
    )
    for delta_type in delta_types:
        assert f"test_type_map_{delta_type}" in entries, delta_type
