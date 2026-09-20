"""Unit tests for the I/O contract in `schemas.py` (SPEC §3, §9.1, §10)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from table_mcp import schemas as s


def _table_ref() -> s.TableRef:
    return s.TableRef(catalog="meridian_fin", schema_name="gl", name="trades_plain")


def test_table_ref_fqn() -> None:
    assert _table_ref().fqn == "meridian_fin.gl.trades_plain"


def test_table_ref_accepts_schema_alias_and_round_trips() -> None:
    ref = s.TableRef.model_validate(
        {"catalog": "meridian_fin", "schema": "gl", "name": "trades_plain"}
    )
    assert ref.schema_name == "gl"
    assert ref.model_dump(by_alias=True)["schema"] == "gl"


def test_models_forbid_unmodelled_fields() -> None:
    with pytest.raises(ValidationError):
        s.TableRef.model_validate({"catalog": "c", "schema": "s", "name": "t", "surprise_field": 1})


def test_every_tool_input_carries_run_id() -> None:
    """SPEC §3: "All tools accept `run_id`"."""
    inputs = [
        s.DiscoverTablesInput,
        s.ProfileTableInput,
        s.RecommendStrategyInput,
        s.PlanConversionInput,
        s.ExecuteConversionInput,
        s.ValidateReadsInput,
        s.PromoteTableInput,
        s.RollbackTableInput,
        s.GetConversionRecordInput,
    ]
    for model in inputs:
        assert "run_id" in model.model_fields, model.__name__
        assert model.model_fields["run_id"].is_required(), model.__name__


def test_conversion_options_defaults_match_gate_0() -> None:
    """Gate 0 #1/#2/#15: no history by default, re-layout opt-in, CDF window 30."""
    options = s.ConversionOptions()
    assert options.history_days is None
    assert options.history_versions is None
    assert options.relayout is False
    assert options.register_bridge is False
    assert options.cdf_window_days == 30
    assert options.parallelism == 8
    assert options.timestamp_mode is s.TimestampMode.TIMESTAMPTZ


def test_kms_key_is_optional_in_the_model() -> None:
    """SPEC §10 layer 1: absence surfaces as KMS_KEY_REQUIRED from the
    precondition, not as a schema error (AT-15)."""
    assert s.ConversionOptions().kms_key_arn is None
    assert s.ErrorCode.KMS_KEY_REQUIRED in set(s.ErrorCode)


def test_manifest_states_match_spec_section_9() -> None:
    assert {state.value for state in s.TableState} == {
        "PLANNED",
        "RUNNING",
        "STAGED",
        "VALIDATED",
        "PROMOTED",
        "FAILED",
        "ROLLED_BACK",
        "FEDERATED",
        "SKIPPED_S6",
        "MANUAL",
    }


def test_named_warning_codes_from_spec_section_5() -> None:
    for code in (
        "HISTORY_NOT_PRESERVED",
        "HISTORY_TRUNCATED",
        "TYPE_WIDENED",
        "LENGTH_CONSTRAINT_DROPPED",
        "SORT_ORDER_ADVISORY",
        "CDF_WINDOW_TRUNCATED",
        "CDF_UNUSED_DROPPED",
    ):
        assert code in {warning.value for warning in s.WarningCode}


def test_spec_named_error_codes_exist() -> None:
    for code in (
        "ALREADY_PROMOTED",
        "APPROVAL_REQUIRED",
        "APPROVAL_INVALID",
        "LOCKED",
        "RECOVERY_BLOCKED",
    ):
        assert code in {error.value for error in s.ErrorCode}


def _approval_fields() -> dict[str, object]:
    return {
        "approval_id": "ap-1",
        "table_ref": "meridian_fin.gl.trades_plain",
        "plan_id": "plan-1",
        "recon_record_id": "recon-1",
        "approver": "sso:auditor@example.com",
        "approved_at": datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        "decision": "APPROVE",
    }


def test_approval_record_requires_every_field_of_spec_9_1() -> None:
    approval = s.ApprovalRecord.model_validate(_approval_fields())
    assert approval.decision is s.ApprovalDecision.APPROVE

    for field in _approval_fields():
        incomplete = _approval_fields()
        del incomplete[field]
        with pytest.raises(ValidationError):
            s.ApprovalRecord.model_validate(incomplete)


def test_approval_record_table_ref_must_be_fully_qualified() -> None:
    fields = _approval_fields()
    fields["table_ref"] = "gl.trades_plain"
    with pytest.raises(ValidationError):
        s.ApprovalRecord.model_validate(fields)


def test_conversion_record_holds_aggregates_and_tool_output_does_not() -> None:
    """SPEC §8/§10: aggregate values are permitted only in the encrypted record."""
    assert "column_aggregates" in s.ConversionRecord.model_fields
    for model in (
        s.ValidationResult,
        s.TableExecutionResult,
        s.ExecuteConversionOutput,
        s.ValidateReadsOutput,
        s.GetConversionRecordOutput,
    ):
        assert "column_aggregates" not in model.model_fields, model.__name__


def test_get_conversion_record_output_strips_aggregates() -> None:
    """The one tool that returns the record must not carry its data values."""
    record = s.ConversionRecord(
        record_id="rec-1",
        run_id="run-1",
        plan_id="plan-1",
        state=s.TableState.STAGED,
        table_ref=_table_ref(),
        decision=s.StrategyDecision(strategy=s.Strategy.S1, rule_id=s.StrategyRuleId.S1),
        strategy=s.Strategy.S1,
        column_aggregates=[
            s.ColumnAggregate(
                column="notional",
                aggregate="sum",
                source_value="1234567.89",
                target_value="1234567.89",
                matched=True,
            )
        ],
    )
    assert record.column_aggregates

    output = s.GetConversionRecordOutput(run_id="run-1", record=record)
    assert output.record.column_aggregates == []
    assert "1234567.89" not in output.model_dump_json()


def test_identifiers_reject_injection_and_traversal() -> None:
    """Identifiers reach UC SQL, Glue names, S3 keys and OTel attributes."""
    for bad in ("meridian fin", "gl.trades", "a'b", "a\nb", "..", "x" * 256):
        with pytest.raises(ValidationError):
            s.TableRef(catalog=bad, schema_name="gl", name="t")

    for bad in ("../../etc", "run 1", "run\nid", "-leading"):
        with pytest.raises(ValidationError):
            s.ProfileTableInput(run_id=bad, table_ref=_table_ref())


def test_table_ref_always_composes_into_a_valid_fqn() -> None:
    """So that building an ErrorEnvelope from a ref can never itself raise."""
    envelope = s.ErrorEnvelope(code=s.ErrorCode.INTERNAL, message="x", table=_table_ref().fqn)
    assert envelope.table == "meridian_fin.gl.trades_plain"


def test_kms_key_arn_must_be_a_key_arn() -> None:
    """Presence is layer 1 of the KMS enforcement, so presence must mean usable."""
    for bad in ("", "alias/acc", "not-an-arn"):
        with pytest.raises(ValidationError):
            s.ConversionOptions(kms_key_arn=bad)
    good = "arn:aws:kms:eu-west-1:123456789012:key/1234abcd-12ab-34cd-56ef-1234567890ab"
    assert s.ConversionOptions(kms_key_arn=good).kms_key_arn == good


def test_iceberg_transform_is_an_allow_list() -> None:
    """Derived from source metadata and reaches partition-spec DDL (SPEC §5)."""
    for good in ("identity", "year", "bucket[16]", "truncate[8]"):
        assert s.PartitionColumn(name="p", identity=False, iceberg_transform=good)
    for bad in ("year(ts)", "drop table", "bucket[]"):
        with pytest.raises(ValidationError):
            s.PartitionColumn(name="p", identity=False, iceberg_transform=bad)


def test_domain_error_carries_its_spec_named_code() -> None:
    """SPEC §3 refusals must not collapse into INTERNAL."""
    exc = s.TableMcpError(
        s.ErrorCode.APPROVAL_REQUIRED, "no approval record", table="meridian_fin.gl.trades_plain"
    )
    assert exc.code is s.ErrorCode.APPROVAL_REQUIRED
    assert exc.retryable is False


def test_conversion_record_minimal_round_trip() -> None:
    record = s.ConversionRecord(
        record_id="rec-1",
        run_id="run-1",
        plan_id="plan-1",
        state=s.TableState.STAGED,
        table_ref=_table_ref(),
        decision=s.StrategyDecision(strategy=s.Strategy.S1, rule_id=s.StrategyRuleId.S1),
        strategy=s.Strategy.S1,
    )
    restored = s.ConversionRecord.model_validate_json(record.model_dump_json())
    assert restored == record
    assert restored.schema_version == s.SCHEMA_VERSION


def test_strategy_s7_is_recorded_as_manual_decision() -> None:
    """SPEC §5 row S7: the rule id is S7, the decision is MANUAL."""
    decision = s.StrategyDecision(
        strategy=s.Strategy.MANUAL,
        rule_id=s.StrategyRuleId.S7,
        manual_reason="VARIANT column has no Iceberg v1 equivalent",
    )
    assert decision.strategy is s.Strategy.MANUAL
    assert "S7" not in {strategy.value for strategy in s.Strategy}
