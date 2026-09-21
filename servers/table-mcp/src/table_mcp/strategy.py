"""The strategy matrix (SPEC §5) and conversion planning (SPEC §3).

`recommend_strategy(profile, options)` is a pure, tested function over a
`TableProfile` — no I/O, no clock, no randomness, so the same input always
yields the same decision (design principle 2).

Decision order is fixed at **S6 → S7 → S5 → S4 → S3 → S2 → S1**; first match
wins, and the rationale lists *every* rule evaluated, matched or not. Never
reorder (server CLAUDE.md).

S5 is a modifier rather than a terminal rule: a DLT-managed table takes strategy
S5 and carries the strategy it would otherwise have had in
`underlying_strategy`.

**Rationale strings are template + enum only** (SPEC §10). No UC-authored text
is interpolated into a `RuleEvaluation.reason`, because those reach an agent
context; source text travels in `StrategyDecision.source_metadata`.

Coverage gate: ≥ 90% on this module. Every rule has `test_strategy_rule_<id>`,
every trigger condition its own test, every order boundary its own test.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from table_mcp import partitioning, types
from table_mcp.sanitize import mark_untrusted
from table_mcp.schemas import (
    ColumnMappingMode,
    ConversionOptions,
    ManualReason,
    PlanConversionInput,
    PlanConversionOutput,
    RecommendStrategyInput,
    RecommendStrategyOutput,
    RuleEvaluation,
    SourceMetadata,
    Strategy,
    StrategyDecision,
    StrategyRuleId,
    StrategyWarning,
    TableProfile,
    TimestampMode,
    WarningCode,
)

__all__ = [
    "DECISION_ORDER",
    "TINY_FILE_COUNT_THRESHOLD",
    "TINY_FILE_MEDIAN_BYTES_THRESHOLD",
    "recommend_strategy",
    "rule_s1",
    "rule_s2",
    "rule_s3",
    "rule_s4",
    "rule_s5",
    "rule_s6",
    "rule_s7",
]

# Fixed evaluation order of SPEC §5. Read by the order-boundary tests.
DECISION_ORDER: Final[tuple[StrategyRuleId, ...]] = (
    StrategyRuleId.S6,
    StrategyRuleId.S7,
    StrategyRuleId.S5,
    StrategyRuleId.S4,
    StrategyRuleId.S3,
    StrategyRuleId.S2,
    StrategyRuleId.S1,
)

# Tiny-file pathology (SPEC §5, AT-09). Both conditions must hold, and both
# are strict: ">10,000 files AND median file size <8 MB", read as MiB.
TINY_FILE_COUNT_THRESHOLD: Final[int] = 10_000
TINY_FILE_MEDIAN_BYTES_THRESHOLD: Final[int] = 8 * 1024 * 1024


@dataclass(frozen=True)
class RuleResult:
    """One rule's verdict: whether it matched, and why.

    `reason` is template + enum text only — never source text (SPEC §10).
    """

    rule_id: StrategyRuleId
    matched: bool
    reason: str
    manual_reason: ManualReason | None = None
    triggers: tuple[str, ...] = field(default=())

    def as_evaluation(self) -> RuleEvaluation:
        return RuleEvaluation(
            rule_id=self.rule_id,
            matched=self.matched,
            reason=self.reason,
            triggers=list(self.triggers),
        )


# --------------------------------------------------------------------------- #
# Rules, in decision order
# --------------------------------------------------------------------------- #


def rule_s6(profile: TableProfile, options: ConversionOptions) -> RuleResult:
    """S6 — the table already exposes Iceberg metadata via UniForm.

    Not converted: the existing metadata location is registered in Glue as a
    read-only bridge, or nothing happens at all when `register_bridge` is unset
    (AT-22).
    """
    del options
    if profile.features.uniform_iceberg:
        return RuleResult(
            StrategyRuleId.S6,
            True,
            "UniForm Iceberg metadata is enabled; federate now, convert at cut-over",
            triggers=("uniform_iceberg",),
        )
    return RuleResult(StrategyRuleId.S6, False, "no UniForm Iceberg metadata")


def rule_s7(profile: TableProfile, options: ConversionOptions) -> RuleResult:
    """S7 — protocol features this version cannot handle, or a corrupted log.

    Four triggers (SPEC §5): a corrupted log; a column type with no Iceberg
    equivalent; row tracking with a downstream dependency; a recorded type
    widening that cannot be represented.
    """
    del options
    if profile.log_corrupted:
        return RuleResult(
            StrategyRuleId.S7,
            True,
            "the Delta log is corrupted or unreadable",
            manual_reason=ManualReason.CORRUPTED_LOG,
            triggers=("log_corrupted",),
        )

    for column in profile.columns:
        reason = types.unmappable_reason(column.delta_type)
        if reason is not None:
            return RuleResult(
                StrategyRuleId.S7,
                True,
                f"a column type has no Iceberg equivalent in v1 ({reason.value})",
                manual_reason=reason,
                triggers=("unmappable_type",),
            )

    if profile.features.row_tracking and profile.downstream_consumers:
        return RuleResult(
            StrategyRuleId.S7,
            True,
            "row tracking is enabled and lineage shows a downstream dependency",
            manual_reason=ManualReason.ROW_TRACKING_DEPENDENCY,
            triggers=("row_tracking_dependency",),
        )

    if profile.features.type_widening_unsupported:
        return RuleResult(
            StrategyRuleId.S7,
            True,
            "a recorded type widening cannot be represented in Iceberg",
            manual_reason=ManualReason.TYPE_WIDENING_NOT_REPRESENTABLE,
            triggers=("type_widening_unsupported",),
        )

    return RuleResult(StrategyRuleId.S7, False, "no unsupported protocol feature or type")


def rule_s5(profile: TableProfile, options: ConversionOptions) -> RuleResult:
    """S5 — DLT-managed. A *modifier*: the underlying rule still runs (AT-06)."""
    del options
    if profile.dlt_managed:
        return RuleResult(
            StrategyRuleId.S5,
            True,
            "the table is DLT-managed; its pipeline must migrate before promotion",
            triggers=("dlt_managed",),
        )
    return RuleResult(StrategyRuleId.S5, False, "not DLT-managed")


def rule_s4(profile: TableProfile, options: ConversionOptions) -> RuleResult:
    """S4 — CDF enabled **and** lineage shows a `table_changes()` consumer.

    CDF with no consumer is not S4: it routes on to S3/S1 and drops the feed
    with `CDF_UNUSED_DROPPED` (SPEC §5).
    """
    del options
    if not profile.features.change_data_feed:
        return RuleResult(StrategyRuleId.S4, False, "Change Data Feed is not enabled")
    if not profile.cdf_consumers:
        return RuleResult(
            StrategyRuleId.S4,
            False,
            "Change Data Feed is enabled but lineage shows no table_changes() consumer",
        )
    return RuleResult(
        StrategyRuleId.S4,
        True,
        "Change Data Feed is enabled and lineage shows a table_changes() consumer",
        triggers=("cdf_with_consumer",),
    )


def rule_s3(profile: TableProfile, options: ConversionOptions) -> RuleResult:
    """S3 — rewrite. Any one of the SPEC §5 triggers forces a compacting copy.

    Each trigger is reported separately so the rationale and the client report
    say *which* feature cost the zero-copy path.
    """
    triggers: list[str] = []
    if profile.features.deletion_vectors:
        triggers.append("deletion_vectors")
    if profile.features.column_mapping is ColumnMappingMode.ID:
        triggers.append("column_mapping_id_mode")
    if profile.features.generated_columns:
        triggers.append("generated_columns")
    if profile.features.identity_columns:
        triggers.append("identity_columns")
    if not partitioning.is_identity_only(profile):
        triggers.append("non_identity_partition_scheme")
    if (
        profile.active_file_count > TINY_FILE_COUNT_THRESHOLD
        and profile.median_file_size_bytes < TINY_FILE_MEDIAN_BYTES_THRESHOLD
    ):
        triggers.append("tiny_file_pathology")
    if options.relayout:
        triggers.append("relayout_requested")
    if options.timestamp_mode is TimestampMode.NTZ_UTC:
        triggers.append("timestamp_mode_ntz_utc")

    if triggers:
        return RuleResult(
            StrategyRuleId.S3,
            True,
            f"rewrite required by: {', '.join(triggers)}",
            triggers=tuple(triggers),
        )
    return RuleResult(StrategyRuleId.S3, False, "no rewrite trigger present")


def rule_s2(profile: TableProfile, options: ConversionOptions) -> RuleResult:
    """S2 — S1-eligible **and** the client explicitly asked for history.

    History is opt-in: both options default to null, so S1 stays the common case
    (Gate 0 #1, AT-01).
    """
    del profile
    if options.history_days is None and options.history_versions is None:
        return RuleResult(StrategyRuleId.S2, False, "no history window requested; default is none")
    return RuleResult(
        StrategyRuleId.S2,
        True,
        "history was requested and the table is metadata-replayable",
        triggers=("history_requested",),
    )


def rule_s1(profile: TableProfile, options: ConversionOptions) -> RuleResult:
    """S1 — metadata-only snapshot. The terminal rule: it always matches."""
    del profile, options
    return RuleResult(
        StrategyRuleId.S1,
        True,
        "no Delta feature blocks add_files; register existing Parquet with zero copy",
        triggers=("metadata_only",),
    )


_TERMINAL_RULES: Final[tuple[tuple[StrategyRuleId, Strategy], ...]] = (
    (StrategyRuleId.S4, Strategy.S4),
    (StrategyRuleId.S3, Strategy.S3),
    (StrategyRuleId.S2, Strategy.S2),
    (StrategyRuleId.S1, Strategy.S1),
)

_Rule = Callable[[TableProfile, ConversionOptions], RuleResult]

_RULES: Final[dict[StrategyRuleId, _Rule]] = {
    StrategyRuleId.S6: rule_s6,
    StrategyRuleId.S7: rule_s7,
    StrategyRuleId.S5: rule_s5,
    StrategyRuleId.S4: rule_s4,
    StrategyRuleId.S3: rule_s3,
    StrategyRuleId.S2: rule_s2,
    StrategyRuleId.S1: rule_s1,
}


# --------------------------------------------------------------------------- #
# Warnings (SPEC §5, named codes)
# --------------------------------------------------------------------------- #


def _history_requested(options: ConversionOptions) -> bool:
    return options.history_days is not None or options.history_versions is not None


def _effective_history_floor(profile: TableProfile) -> int | None:
    """Oldest Delta version that can still be replayed (SPEC §6).

    S2 replays oldest→newest with `add_files`/`delete_files` per version, so the
    window must be **contiguous**: a vacuumed version anywhere below a candidate
    floor makes that floor unreachable, not merely sparse. The floor is
    therefore the start of the unbroken recoverable run that ends at the latest
    version — for `[v0 present, v1 vacuumed, v2 present]` it is v2, not v0.
    """
    ledger = sorted(profile.version_ledger, key=lambda entry: entry.version, reverse=True)
    floor: int | None = None
    for entry in ledger:
        if not entry.recoverable:
            break
        floor = entry.version
    return floor


def _collect_warnings(
    profile: TableProfile, options: ConversionOptions, strategy: Strategy
) -> list[StrategyWarning]:
    """Every named warning of SPEC §5 that applies to this decision.

    Only the converting strategies get warnings. S6 federates the existing
    Iceberg metadata and MANUAL converts nothing, so telling the client that a
    CHAR column would lose its length constraint describes a conversion that is
    not going to happen. It also means the type loop below runs only after rule
    S7 has confirmed every column is mappable, so no mapping failure can be
    swallowed here — the bug that let an unmappable column reach S1.
    """
    warnings: list[StrategyWarning] = []
    if strategy in {Strategy.S6, Strategy.MANUAL}:
        return warnings

    if _history_requested(options) and strategy in {Strategy.S3, Strategy.S4}:
        warnings.append(
            StrategyWarning(
                code=WarningCode.HISTORY_NOT_PRESERVED,
                detail="history was requested but a rewrite strategy was chosen; "
                "prior Delta versions are recorded as metadata only",
            )
        )

    if strategy is Strategy.S2:
        floor = _effective_history_floor(profile)
        unrecoverable = [entry.version for entry in profile.version_ledger if not entry.recoverable]
        # Any vacuumed version below the floor truncates the window, whether it
        # sits at the start of the ledger or leaves a gap in the middle (§6).
        if unrecoverable and (floor is None or min(unrecoverable) < floor):
            warnings.append(
                StrategyWarning(
                    code=WarningCode.HISTORY_TRUNCATED,
                    detail=f"replay window truncated at version {floor}; "
                    f"{len(unrecoverable)} vacuumed version(s) cannot be reproduced",
                )
            )

    if profile.features.change_data_feed and not profile.cdf_consumers:
        warnings.append(
            StrategyWarning(
                code=WarningCode.CDF_UNUSED_DROPPED,
                detail="Change Data Feed is enabled but no table_changes() consumer was found; "
                "the feed is not carried across",
            )
        )

    if strategy is Strategy.S4:
        retention = profile.features.cdf_retention_days
        if retention is not None and retention < options.cdf_window_days:
            warnings.append(
                StrategyWarning(
                    code=WarningCode.CDF_WINDOW_TRUNCATED,
                    detail=f"requested changelog window of {options.cdf_window_days} days exceeds "
                    f"the Delta CDF retention of {retention} days",
                )
            )

    if options.timestamp_mode is TimestampMode.NTZ_UTC:
        warnings.append(
            StrategyWarning(
                code=WarningCode.TIMESTAMP_MODE,
                detail="timestamp_mode=ntz_utc maps TIMESTAMP to timestamp normalised to UTC",
            )
        )

    widened: list[str] = []
    length_dropped: list[str] = []
    for column in profile.columns:
        # Safe without a guard: rule S7 refuses any unmappable column before a
        # converting strategy can be chosen.
        mapped = types.map_type(
            column.delta_type, column=column.name, timestamp_mode=options.timestamp_mode
        )
        if mapped.type_widened:
            widened.append(column.name)
        if mapped.length_constraint_dropped:
            length_dropped.append(column.name)

    if widened:
        warnings.append(
            StrategyWarning(
                code=WarningCode.TYPE_WIDENED,
                detail=f"{len(widened)} column(s) widen to a larger Iceberg type",
            )
        )
    if length_dropped:
        warnings.append(
            StrategyWarning(
                code=WarningCode.LENGTH_CONSTRAINT_DROPPED,
                detail=f"{len(length_dropped)} CHAR/VARCHAR column(s) lose their length constraint",
            )
        )

    if partitioning.advisory_sort_order(profile):
        warnings.append(
            StrategyWarning(
                code=WarningCode.SORT_ORDER_ADVISORY,
                detail="liquid clustering maps to an Iceberg sort order, which is advisory "
                "rather than a clustering guarantee",
            )
        )

    return warnings


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


def decide(profile: TableProfile, options: ConversionOptions) -> StrategyDecision:
    """Evaluate every rule in order and build the decision (SPEC §5).

    Pure: no I/O, no clock. The rationale carries one `RuleEvaluation` per rule
    considered, in decision order, so a reviewer can see what was ruled out.
    """
    rationale: list[RuleEvaluation] = []

    s6 = rule_s6(profile, options)
    rationale.append(s6.as_evaluation())
    if s6.matched:
        eventual = Strategy.S3 if _would_rewrite(profile, options) else Strategy.S1
        return StrategyDecision(
            strategy=Strategy.S6,
            rule_id=StrategyRuleId.S6,
            rationale=rationale,
            warnings=_collect_warnings(profile, options, Strategy.S6),
            eventual_strategy=eventual,
            source_metadata=_source_metadata(profile),
        )

    s7 = rule_s7(profile, options)
    rationale.append(s7.as_evaluation())
    if s7.matched:
        return StrategyDecision(
            strategy=Strategy.MANUAL,
            rule_id=StrategyRuleId.S7,
            rationale=rationale,
            warnings=_collect_warnings(profile, options, Strategy.MANUAL),
            manual_reason=s7.manual_reason,
            manual_detail=s7.reason,
            source_metadata=_source_metadata(profile),
        )

    s5 = rule_s5(profile, options)
    rationale.append(s5.as_evaluation())

    underlying = Strategy.S1
    for rule_id, strategy in _TERMINAL_RULES:
        rule = _RULES[rule_id]
        result = rule(profile, options)
        rationale.append(result.as_evaluation())
        if result.matched:
            underlying = strategy
            break

    chosen = Strategy.S5 if s5.matched else underlying
    return StrategyDecision(
        strategy=chosen,
        rule_id=StrategyRuleId.S5 if s5.matched else _rule_id_for(underlying),
        rationale=rationale,
        warnings=_collect_warnings(profile, options, underlying),
        underlying_strategy=underlying if s5.matched else None,
        source_metadata=_source_metadata(profile),
    )


def _would_rewrite(profile: TableProfile, options: ConversionOptions) -> bool:
    """Whether a non-UniForm table would need S3 — the S6 eventual strategy."""
    return rule_s3(profile, options).matched


def _rule_id_for(strategy: Strategy) -> StrategyRuleId:
    return StrategyRuleId(strategy.value)


def _source_metadata(profile: TableProfile) -> SourceMetadata:
    """Carry UC-authored text apart from the rationale, and mark it (SPEC §10).

    `StrategyDecision` is returned straight to the MCP caller, so this text
    reaches a model context and §10 requires the
    `<x-untrusted src="uc:{field}">…</x-untrusted>` marker. The values are
    already sanitised at the model boundary; marking is what tells the reader
    the content is data, not instruction.

    Glue parameters (SPEC §7) take the sanitised value *without* the marker —
    that is presentation for a model, and would corrupt what a client reads back
    from the catalogue.
    """
    return SourceMetadata(
        table_comment=(
            mark_untrusted(profile.comment, field="comment") if profile.comment else None
        ),
        column_comments={
            column.name: mark_untrusted(column.comment, field=f"column_comment:{column.name}")
            for column in profile.columns
            if column.comment
        },
        uc_tags={
            key: mark_untrusted(value, field=f"tag:{key}") for key, value in profile.uc_tags.items()
        },
        constraints={
            name: mark_untrusted(expression, field=f"constraint:{name}")
            for name, expression in profile.features.constraints.items()
        },
        generated_expressions={
            column.name: mark_untrusted(
                column.generated_expression, field=f"generated_expression:{column.name}"
            )
            for column in profile.columns
            if column.generated_expression
        },
    )


def recommend_strategy(params: RecommendStrategyInput) -> RecommendStrategyOutput:
    """Return the `StrategyDecision` for a profile. Pure function, no I/O."""
    return RecommendStrategyOutput(
        run_id=params.run_id,
        table_ref=params.profile.table_ref,
        decision=decide(params.profile, params.options),
    )


def plan_conversion(params: PlanConversionInput) -> PlanConversionOutput:
    """Build a `ConversionPlan`: per-table strategy, ordering, parallelism,
    staging locations and estimated totals. No side effects (SPEC §3)."""
    raise NotImplementedError("SPEC §3 plan_conversion")
