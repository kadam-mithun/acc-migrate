"""The committed JSON Schemas are the cross-service contract (SPEC §9.1, §10).

`schemas/approval_record.json` is shared with `gov-mcp`, `aws-mcp` and the
Console, and `schemas/conversion_record.json` describes the evidence record.
Both must stay in step with the Pydantic models that produce and consume them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from table_mcp.schemas import ApprovalRecord, ConversionRecord

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


@pytest.mark.parametrize(
    ("filename", "model"),
    [
        ("approval_record.json", ApprovalRecord),
        ("conversion_record.json", ConversionRecord),
    ],
)
def test_committed_schema_matches_model(filename: str, model: type) -> None:
    committed = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    assert committed == model.model_json_schema(), (
        f"{filename} is stale — regenerate it with `uv run python -m table_mcp.schemas`"
    )


def test_approval_schema_requires_every_field_of_spec_9_1() -> None:
    committed = json.loads((SCHEMA_DIR / "approval_record.json").read_text(encoding="utf-8"))
    assert set(committed["required"]) == {
        "approval_id",
        "table_ref",
        "plan_id",
        "recon_record_id",
        "approver",
        "approved_at",
        "decision",
    }
