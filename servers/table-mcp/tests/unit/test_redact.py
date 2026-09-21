"""Error wrapping through the redaction layer (SPEC §3, §10; AT-18)."""

from __future__ import annotations

import pytest

from table_mcp.redact import to_error_envelope
from table_mcp.schemas import ErrorCode


def test_error_envelope_withholds_the_library_message() -> None:
    """Until SPEC §10 scrubbing is implemented the envelope carries the exception
    class name only, so a literal in the message cannot reach a log."""
    # Synthetic, not sampled from any fixture estate (root rule 4).
    message_with_literals = "trade_date='2026-01-01' account='ACME-001'"
    envelope = to_error_envelope(
        ValueError(message_with_literals), table="meridian_fin.gl.trades_plain"
    )

    assert envelope.code is ErrorCode.INTERNAL
    assert "ValueError" in envelope.message
    assert message_with_literals not in envelope.message
    assert "ACME-001" not in envelope.message
    assert "'" not in envelope.message
    assert envelope.table == "meridian_fin.gl.trades_plain"


def test_error_code_can_be_overridden() -> None:
    envelope = to_error_envelope(RuntimeError("boom"), code=ErrorCode.LOCKED)
    assert envelope.code is ErrorCode.LOCKED
    assert envelope.retryable is False


def test_validation_error_reports_field_names_only() -> None:
    """SPEC §10: "Pydantic validation errors report field names only"."""
    from pydantic import ValidationError

    from table_mcp.redact import validation_error_envelope
    from table_mcp.schemas import ProfileTableInput

    try:
        ProfileTableInput.model_validate(
            {"run_id": "../secret-run", "table_ref": {"catalog": "c", "schema": "s", "name": "t"}}
        )
    except ValidationError as exc:
        envelope = validation_error_envelope(exc)
    else:  # pragma: no cover - the input above is invalid by construction
        pytest.fail("expected a ValidationError")

    assert "run_id" in envelope.message
    assert "../secret-run" not in envelope.message
    assert "input_value" not in envelope.message
    assert envelope.hint is not None
    assert "../secret-run" not in envelope.hint


def test_safe_table_tag_drops_a_malformed_tag_instead_of_raising() -> None:
    """A tag that fails the FQN pattern must not make the error path itself fail."""
    from table_mcp.redact import safe_table_tag

    assert safe_table_tag("meridian_fin.gl.trades") == "meridian_fin.gl.trades"
    assert safe_table_tag("not an fqn") is None
    assert safe_table_tag(None) is None


def test_domain_error_envelope_keeps_the_spec_named_code() -> None:
    from table_mcp.errors import ApprovalRequiredError, TableMcpError
    from table_mcp.redact import domain_error_envelope

    envelope = domain_error_envelope(ApprovalRequiredError("approval_id is required"))
    assert envelope.code is ErrorCode.APPROVAL_REQUIRED
    assert envelope.message == "approval_id is required"

    generic = domain_error_envelope(TableMcpError("boom", code=ErrorCode.LOCKED))
    assert generic.code is ErrorCode.LOCKED
