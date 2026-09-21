"""Pydantic I/O models for `table-mcp`.

Covers every tool in SPEC §3, the conversion record in SPEC §10 and the
promotion approval record in SPEC §9.1.

Rules that shape this module:

* Models are the only I/O contract; `server.py` registers tools against them and
  holds no logic (SPEC §13).
* Column aggregates are **data values** (SPEC §8). They appear on
  :class:`ConversionRecord` only — which is written encrypted to the client
  bucket — and never on a tool response or anything the redaction layer logs.
* `extra="forbid"` everywhere: an unmodelled field from an upstream library is a
  validation error, not a silent passthrough into evidence.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from table_mcp.sanitize import sanitize_source_text

# Fully-qualified `catalog.schema.table`, used where a cross-service contract
# needs a scalar table identity (SPEC §9.1).
TABLE_FQN_PATTERN = r"^[^.\s]+\.[^.\s]+\.[^.\s]+$"
TableFqn = Annotated[str, Field(pattern=TABLE_FQN_PATTERN)]

# Unity Catalog identifiers. Constrained so that (a) a `TableRef` always composes
# into a valid `TableFqn`, (b) no identifier can carry a quote, dot, newline or
# control character into a UC SQL statement, a Glue name, an S3 key or an OTel
# attribute. See OPEN_QUESTIONS #8 on non-standard (backtick-quoted) UC names.
IDENTIFIER_PATTERN = r"^[A-Za-z0-9_-]{1,255}$"
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]

# `run_id`, `plan_id` and record ids reach S3 key paths — `acc-migrate/evidence/
# {run_id}/{table}.json` (SPEC §10) and the deterministic staging prefix per
# `plan_id` (SPEC §9). Constrained against key traversal and log injection.
RUN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
RunId = Annotated[str, Field(pattern=RUN_ID_PATTERN)]

# A KMS **key** ARN, not an alias: layer 1 of the KMS enforcement checks presence
# (SPEC §10), and this makes presence mean a usable CMK.
KMS_KEY_ARN_PATTERN = r"^arn:aws[a-zA-Z-]*:kms:[a-z0-9-]+:\d{12}:key/[A-Za-z0-9-]+$"
KmsKeyArn = Annotated[str, Field(pattern=KMS_KEY_ARN_PATTERN)]

# The Iceberg transform grammar (SPEC §5 partitioning). An allow-list, because
# this value is derived from source metadata and reaches partition-spec DDL.
ICEBERG_TRANSFORM_PATTERN = r"^(identity|void|year|month|day|hour|bucket\[\d+\]|truncate\[\d+\])$"

# UC-authored text (comments, tags, constraints, generated expressions). The
# validator runs at the model boundary, so a model carrying raw source text
# cannot be constructed (SPEC §10, §14 row 26).
UntrustedText = Annotated[str, BeforeValidator(sanitize_source_text)]


def is_supported_identifier(value: str) -> bool:
    """True when `value` is a UC identifier this version can handle.

    A non-conforming identifier is **not** dropped: SPEC §14 row 23 makes it an
    S7 decision with reason `UNSUPPORTED_IDENTIFIER`, reported through
    :class:`UnsupportedTable` so `assess-mcp` can count it. Backtick-quoted
    identifier support is v1.1.
    """
    return re.match(IDENTIFIER_PATTERN, value) is not None


SCHEMA_VERSION = "0.3.1"


class _Base(BaseModel):
    """Shared model configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class Strategy(StrEnum):
    """Conversion strategies of SPEC §5.

    S7 ("unsupported — manual") is a *rule* id whose decision is ``MANUAL``; the
    spec states `StrategyDecision.strategy = MANUAL` for that row, so the rule id
    is carried separately in :attr:`StrategyDecision.rule_id`.
    """

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    MANUAL = "MANUAL"


class StrategyRuleId(StrEnum):
    """Rule identifiers, in the decision order of SPEC §5."""

    S6 = "S6"
    S7 = "S7"
    S5 = "S5"
    S4 = "S4"
    S3 = "S3"
    S2 = "S2"
    S1 = "S1"


class TableState(StrEnum):
    """Run-manifest states (SPEC §9)."""

    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    STAGED = "STAGED"
    VALIDATED = "VALIDATED"
    PROMOTED = "PROMOTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    FEDERATED = "FEDERATED"
    SKIPPED_S6 = "SKIPPED_S6"
    MANUAL = "MANUAL"


class WarningCode(StrEnum):
    """Stable warning codes (SPEC §5)."""

    HISTORY_NOT_PRESERVED = "HISTORY_NOT_PRESERVED"
    HISTORY_TRUNCATED = "HISTORY_TRUNCATED"
    TYPE_WIDENED = "TYPE_WIDENED"
    LENGTH_CONSTRAINT_DROPPED = "LENGTH_CONSTRAINT_DROPPED"
    SORT_ORDER_ADVISORY = "SORT_ORDER_ADVISORY"
    CDF_WINDOW_TRUNCATED = "CDF_WINDOW_TRUNCATED"
    CDF_UNUSED_DROPPED = "CDF_UNUSED_DROPPED"
    TIMESTAMP_MODE = "TIMESTAMP_MODE"


class ErrorCode(StrEnum):
    """`ErrorEnvelope.code` values.

    The first block is named normatively by the spec; the second block is the
    scaffold's structured vocabulary for preconditions the spec requires to fail
    (SPEC §4, §9, §10, AT-13 … AT-15).
    """

    ALREADY_PROMOTED = "ALREADY_PROMOTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    LOCKED = "LOCKED"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"

    KMS_KEY_REQUIRED = "KMS_KEY_REQUIRED"
    WRITE_GRANT_PRESENT = "WRITE_GRANT_PRESENT"
    PREFIX_OVERLAP = "PREFIX_OVERLAP"
    ACTIVE_WRITER = "ACTIVE_WRITER"
    DLT_PIPELINE_ACTIVE = "DLT_PIPELINE_ACTIVE"
    UNSUPPORTED_TABLE = "UNSUPPORTED_TABLE"
    PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    ENGINE_DISAGREEMENT = "ENGINE_DISAGREEMENT"
    INTERNAL = "INTERNAL"


class ManualReason(StrEnum):
    """Why a table routed to rule S7 (`strategy = MANUAL`).

    Values are the exact spellings SPEC §5 and §14 use; the casing is
    inconsistent in the spec itself and is reproduced rather than normalised so
    the strings match what `assess-mcp` and the client report expect.
    """

    UNSUPPORTED_IDENTIFIER = "UNSUPPORTED_IDENTIFIER"
    UNSUPPORTED_TYPE = "unsupported_type"
    VOID_COLUMN = "void_column"
    ROW_TRACKING_DEPENDENCY = "row_tracking_dependency"
    TYPE_WIDENING_NOT_REPRESENTABLE = "type_widening_not_representable"
    CORRUPTED_LOG = "corrupted_log"


class ColumnMappingMode(StrEnum):
    """Delta `delta.columnMapping.mode`."""

    NONE = "none"
    NAME = "name"
    ID = "id"


class TimestampMode(StrEnum):
    """`options.timestamp_mode` (SPEC §5, Gate 0 #18)."""

    TIMESTAMPTZ = "timestamptz"
    NTZ_UTC = "ntz_utc"


class ReadEngine(StrEnum):
    """Engines `validate_reads` must agree across (SPEC §8)."""

    ATHENA = "athena"
    REDSHIFT = "redshift"
    EMR_SPARK = "emr_spark"


class RedshiftReadPath(StrEnum):
    """Which Redshift path served the read (Gate 0 #3)."""

    NATIVE_GLUE = "native_glue"
    SPECTRUM = "spectrum"


class ApprovalDecision(StrEnum):
    """`decision` on the approval record (SPEC §9.1)."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ErrorEnvelope(_Base):
    """Structured error returned by every tool (SPEC §3).

    `message` and `hint` are emitted through `redact.py`: they carry no quoted
    literals, column values or partition values (SPEC §10, AT-18).
    """

    code: ErrorCode
    message: str
    retryable: bool = False
    table: TableFqn | None = None
    hint: str | None = None


# --------------------------------------------------------------------------- #
# Table identity and discovery
# --------------------------------------------------------------------------- #


class TableRef(_Base):
    """The identity of a Delta table in Unity Catalog — nothing else.

    Frozen and identity-only per SPEC §3 and §14 row 21. Every table-scoped tool
    takes this type; only `discover_tables` returns :class:`DiscoveredTable`, so
    no tool can be handed a half-populated ref whose discovery attributes are
    silently `None`.

    Being frozen also makes it hashable, so a ref is usable as a dict key in the
    plan and the manifest without a defensive copy.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    catalog: Identifier
    schema_name: Identifier = Field(alias="schema")
    name: Identifier

    @property
    def fqn(self) -> str:
        """`catalog.schema.table`."""
        return f"{self.catalog}.{self.schema_name}.{self.name}"


class DiscoveredTable(_Base):
    """A `TableRef` plus what discovery learned about it (SPEC §3).

    Returned only by `discover_tables`. Everything past `table_ref` is an
    attribute of the source table, not part of its identity.
    """

    table_ref: TableRef
    location: str | None = Field(default=None, description="Source S3 URI of the Delta table")
    table_format: str | None = Field(default=None, description='Source format, e.g. "DELTA"')
    format_details: dict[str, str] = Field(default_factory=dict)
    size_bytes: int | None = Field(default=None, ge=0)
    last_modified: datetime | None = None
    managed: bool | None = Field(default=None, description="True = UC managed, False = external")
    dlt_managed: bool | None = None
    comment: UntrustedText | None = None
    uc_tags: dict[UntrustedText, UntrustedText] = Field(default_factory=dict)


class UnsupportedTable(_Base):
    """A source table this version cannot name (SPEC §14 row 23).

    Reported, never dropped: the raw identifier parts are sanitised source text,
    so they are safe to display and count, and the decision is S7 `MANUAL` with
    reason `UNSUPPORTED_IDENTIFIER`. `assess-mcp` counts these per estate so a
    client exception surfaces at assessment rather than at conversion.
    """

    catalog: UntrustedText
    schema_name: UntrustedText = Field(alias="schema")
    name: UntrustedText
    reason: ManualReason = ManualReason.UNSUPPORTED_IDENTIFIER
    detail: str | None = None


# --------------------------------------------------------------------------- #
# Profile (SPEC §3 `profile_table`)
# --------------------------------------------------------------------------- #


class DeltaProtocol(_Base):
    """Delta protocol versions and named table features."""

    min_reader_version: int
    min_writer_version: int
    reader_features: list[str] = Field(default_factory=list)
    writer_features: list[str] = Field(default_factory=list)


class TableFeatures(_Base):
    """Delta table features that drive the strategy matrix (SPEC §5)."""

    deletion_vectors: bool = False
    column_mapping: ColumnMappingMode = ColumnMappingMode.NONE
    change_data_feed: bool = False
    cdf_retention_days: int | None = Field(default=None, ge=0)
    liquid_clustering: bool = False
    clustering_columns: list[str] = Field(default_factory=list)
    generated_columns: list[str] = Field(default_factory=list)
    identity_columns: list[str] = Field(default_factory=list)
    constraints: dict[str, UntrustedText] = Field(default_factory=dict)
    row_tracking: bool = False
    type_widening: bool = False
    uniform_iceberg: bool = Field(
        default=False, description="UniForm Iceberg metadata enabled (S6)"
    )
    uniform_metadata_location: str | None = None


class ColumnProfile(_Base):
    """One column of the current Delta schema."""

    name: str
    delta_type: str
    nullable: bool = True
    comment: UntrustedText | None = None
    generated_expression: UntrustedText | None = None
    is_identity: bool = False


class PartitionColumn(_Base):
    """A Delta partition column and the Iceberg transform it maps to."""

    name: str
    identity: bool = Field(description="False for generated/transformed partitions → S3 (SPEC §5)")
    source_column: str | None = None
    generated_expression: UntrustedText | None = None
    iceberg_transform: str | None = Field(
        default=None,
        pattern=ICEBERG_TRANSFORM_PATTERN,
        description='Iceberg transform name, e.g. "year" or "bucket[16]"',
    )


class DeltaVersionEntry(_Base):
    """One entry of the Delta version ledger (SPEC §6)."""

    version: int = Field(ge=0)
    timestamp: datetime
    operation: str
    operation_parameters: dict[str, str] = Field(default_factory=dict, alias="operationParameters")
    file_set_hash: str
    recoverable: bool = Field(default=True, description="False once vacuumed (SPEC §6)")


class SchemaChange(_Base):
    """A schema evolution event in the Delta log (AT-04)."""

    version: int = Field(ge=0)
    timestamp: datetime
    change: str


class TableProfile(_Base):
    """Deep inspection of the Delta log (SPEC §3 `profile_table`)."""

    table_ref: TableRef
    protocol: DeltaProtocol
    features: TableFeatures
    columns: list[ColumnProfile] = Field(default_factory=list)
    partition_columns: list[PartitionColumn] = Field(default_factory=list)
    schema_history: list[SchemaChange] = Field(default_factory=list)
    version_ledger: list[DeltaVersionEntry] = Field(default_factory=list)

    version_count: int = Field(ge=0)
    oldest_version: int | None = Field(default=None, ge=0)
    latest_version: int = Field(ge=0)
    oldest_version_timestamp: datetime | None = None
    latest_version_timestamp: datetime | None = None

    active_file_count: int = Field(ge=0)
    tombstone_count: int = Field(default=0, ge=0)
    total_size_bytes: int = Field(ge=0)
    median_file_size_bytes: int = Field(default=0, ge=0)

    dlt_managed: bool = False
    dlt_pipeline_id: str | None = None
    dlt_pipeline_paused: bool | None = None
    streaming_continuous: bool = False
    last_write_timestamp: datetime | None = None

    cdf_consumers: list[str] = Field(
        default_factory=list, description="Downstream table_changes() consumers from lineage (S4)"
    )
    unsupported_types: list[str] = Field(
        default_factory=list, description="Types with no Iceberg mapping → S7 (SPEC §5)"
    )
    uc_tags: dict[UntrustedText, UntrustedText] = Field(default_factory=dict)
    comment: UntrustedText | None = None


# --------------------------------------------------------------------------- #
# Strategy (SPEC §3 `recommend_strategy`, §5)
# --------------------------------------------------------------------------- #


class RuleEvaluation(_Base):
    """One rule considered by `recommend_strategy`.

    SPEC §5: "rationale lists every rule evaluated" — so both matches and
    non-matches are recorded, in decision order.
    """

    rule_id: StrategyRuleId
    matched: bool
    reason: str


class StrategyWarning(_Base):
    """A named warning copied into the conversion record and client report."""

    code: WarningCode
    detail: str


class CostEstimate(_Base):
    """Estimated cost of a conversion (SPEC §12)."""

    emr_vcpu_hours: float = Field(default=0.0, ge=0)
    s3_get_requests: int = Field(default=0, ge=0)
    s3_put_requests: int = Field(default=0, ge=0)
    estimated_usd: float | None = Field(default=None, ge=0)


class SourceMetadata(_Base):
    """UC-authored text, carried apart from anything a model is told to obey.

    SPEC §10: rationale strings are template + enum only and never interpolate
    source text; it travels here instead, already sanitised by the model
    boundary, and is marked with `sanitize.mark_untrusted` wherever it can reach
    a model context.
    """

    table_comment: UntrustedText | None = None
    column_comments: dict[str, UntrustedText] = Field(default_factory=dict)
    uc_tags: dict[UntrustedText, UntrustedText] = Field(default_factory=dict)
    constraints: dict[str, UntrustedText] = Field(default_factory=dict)
    generated_expressions: dict[str, UntrustedText] = Field(default_factory=dict)


class StrategyDecision(_Base):
    """`StrategyDecision {strategy, rationale[], warnings[], estimated_duration,
    estimated_cost}` (SPEC §3)."""

    strategy: Strategy
    rule_id: StrategyRuleId
    rationale: list[RuleEvaluation] = Field(default_factory=list)
    warnings: list[StrategyWarning] = Field(default_factory=list)
    estimated_duration_seconds: float | None = Field(default=None, ge=0)
    estimated_cost: CostEstimate = Field(default_factory=CostEstimate)

    underlying_strategy: Strategy | None = Field(
        default=None, description="S5 is a modifier: the strategy it wraps (SPEC §5)"
    )
    eventual_strategy: Strategy | None = Field(
        default=None, description="S6 records the strategy to apply at cut-over"
    )
    manual_reason: ManualReason | None = Field(
        default=None, description="Required when strategy is MANUAL (rule S7)"
    )
    manual_detail: str | None = Field(
        default=None, description="Template + enum text only; never source text (SPEC §10)"
    )
    source_metadata: SourceMetadata = Field(
        default_factory=SourceMetadata,
        description="UC-authored text, sanitised and kept out of the rationale (SPEC §10)",
    )


# --------------------------------------------------------------------------- #
# Options, target, plan (SPEC §3 `plan_conversion`, §4, §14)
# --------------------------------------------------------------------------- #


class EmrCapacity(_Base):
    """Maximum capacity for the shared EMR Serverless application (SPEC §9)."""

    cpu: str = "64 vCPU"
    memory: str = "256 GB"
    disk: str = "1000 GB"


class ConversionOptions(_Base):
    """Caller options.

    `kms_key_arn` is optional *in the model* so that its absence surfaces as
    `KMS_KEY_REQUIRED` from the precondition in `storage.py` rather than as a
    schema validation error (SPEC §10 layer 1, AT-15).
    """

    kms_key_arn: KmsKeyArn | None = Field(
        default=None, description="Client CMK key ARN; required to write (SPEC §10)"
    )

    history_versions: int | None = Field(
        default=None, ge=0, description="Default null = no history"
    )
    history_days: int | None = Field(default=None, ge=0, description="Default null = no history")
    cdf_window_days: int = Field(default=30, ge=0)
    timestamp_mode: TimestampMode = TimestampMode.TIMESTAMPTZ
    relayout: bool = Field(default=False, description="Partition/sort redesign is opt-in (#2)")
    register_bridge: bool = Field(default=False, description="S6 Glue bridge (#13, AT-22)")

    parallelism: int = Field(default=8, ge=1)
    emr_max_capacity: EmrCapacity | None = None
    no_writer_window_minutes: int = Field(default=30, ge=0)
    lease_ttl_minutes: int = Field(default=30, ge=1)
    checksum_column_limit: int = Field(default=20, ge=0)
    float_tolerance: float = Field(default=1e-9, ge=0)


class ConversionTarget(_Base):
    """Where conversion output lands (SPEC §4, §10)."""

    client_bucket: str
    region: str
    staging_prefix: str = "iceberg/staging"
    production_prefix: str = "iceberg"
    evidence_prefix: str = "acc-migrate/evidence"
    athena_results_prefix: str = "acc-migrate/athena-results"
    staging_database_suffix: str = "__staging"
    glue_catalog_id: str | None = None
    athena_workgroup: str | None = None
    redshift_workgroup: str | None = None
    emr_application_id: str | None = None
    run_table: str = "acc_migrate_runs"


class PlanEntry(_Base):
    """One table in a `ConversionPlan`."""

    table_ref: TableRef
    order: int = Field(ge=0)
    decision: StrategyDecision
    staging_location: str
    staging_glue_database: str
    staging_glue_table: str
    production_location: str
    production_glue_database: str
    production_glue_table: str


class PlanTotals(_Base):
    """Estimated totals across the plan (SPEC §12)."""

    table_count: int = Field(ge=0)
    total_size_bytes: int = Field(default=0, ge=0)
    estimated_duration_seconds: float | None = Field(default=None, ge=0)
    estimated_cost: CostEstimate = Field(default_factory=CostEstimate)
    by_strategy: dict[Strategy, int] = Field(default_factory=dict)


class ConversionPlan(_Base):
    """Output of `plan_conversion`; has no side effects (SPEC §3)."""

    plan_id: RunId
    run_id: RunId
    created_at: datetime
    target: ConversionTarget
    options: ConversionOptions
    parallelism: int = Field(ge=1)
    entries: list[PlanEntry] = Field(default_factory=list)
    totals: PlanTotals


# --------------------------------------------------------------------------- #
# Validation (SPEC §8)
# --------------------------------------------------------------------------- #


class ColumnAggregate(_Base):
    """Aggregate for one column.

    **Data values.** Permitted only inside :class:`ConversionRecord`, which is
    written SSE-KMS encrypted to the client bucket. Never logged and never
    returned by a tool (SPEC §8, §10).
    """

    column: str
    aggregate: str = Field(description='"sum" | "count_distinct" | "min" | "max"')
    source_value: str
    target_value: str
    matched: bool


class ValidationResult(_Base):
    """Inline validation before a table is marked `STAGED` (SPEC §8).

    Carries match flags, counts and a hash of the aggregate vector only — the
    aggregate values themselves live on the conversion record.
    """

    row_count_source: int = Field(ge=0)
    row_count_target: int = Field(ge=0)
    row_count_match: bool
    schema_equivalent: bool
    checksum_columns: list[str] = Field(
        default_factory=list, description="≤20, selected deterministically (SPEC §8)"
    )
    checksum_match: bool
    checksum_vector_hash: str
    partition_count_source: int = Field(default=0, ge=0)
    partition_count_target: int = Field(default=0, ge=0)
    partition_distribution_match: bool = True
    float_tolerance: float = Field(default=1e-9, ge=0)


class EngineSchemaField(_Base):
    """One column as reported by a query engine."""

    name: str
    type_name: str


class EngineReadResult(_Base):
    """One engine's leg of `validate_reads` (SPEC §8)."""

    engine: ReadEngine
    succeeded: bool
    row_count: int | None = Field(default=None, ge=0)
    schema_fields: list[EngineSchemaField] = Field(default_factory=list)
    redshift_read_path: RedshiftReadPath | None = Field(
        default=None, description="Recorded for the Redshift leg only (Gate 0 #3)"
    )
    duration_ms: int | None = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Conversion record (SPEC §10) and its parts
# --------------------------------------------------------------------------- #


class SnapshotMapping(_Base):
    """Delta version → Iceberg snapshot, published for time travel (SPEC §6)."""

    delta_version: int = Field(ge=0)
    iceberg_snapshot_id: int
    commit_timestamp: datetime


class TypeMappingRecord(_Base):
    """One applied column type mapping (SPEC §5 type table)."""

    column: str
    delta_type: str
    iceberg_type: str
    type_widened: bool = False
    length_constraint_dropped: bool = False


class CdfDetail(_Base):
    """Change Data Feed handling (SPEC §5, S4)."""

    enabled: bool = False
    consumers: list[str] = Field(default_factory=list)
    changelog_table: str | None = None
    window_days: int | None = Field(default=None, ge=0)
    window_truncated: bool = False


class DltDetail(_Base):
    """DLT provenance carried to `jobs-mcp` (SPEC §5, S5)."""

    managed: bool = False
    pipeline_id: str | None = None
    pipeline_paused: bool | None = None
    flagged_for_jobs_mcp: bool = False
    expectations: dict[str, str] = Field(default_factory=dict)


class BridgeDetail(_Base):
    """UniForm read-only Glue bridge (SPEC §5, S6; AT-22)."""

    registered: bool = False
    source_metadata_location: str | None = None
    glue_bridge_database: str | None = None
    glue_bridge_table: str | None = None


class ActualCost(_Base):
    """Recorded actuals for the learning loop (SPEC §12)."""

    emr_vcpu_hours: float = Field(default=0.0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0)
    s3_get_requests: int = Field(default=0, ge=0)
    s3_put_requests: int = Field(default=0, ge=0)
    actual_usd: float | None = Field(default=None, ge=0)


class ConversionRecord(_Base):
    """Evidence record, one JSON per table (SPEC §10).

    Written to `s3://{client-bucket}/acc-migrate/evidence/{run_id}/{table}.json`
    SSE-KMS encrypted and referenced from the ledger. This is the only object
    permitted to hold column aggregates.
    """

    schema_version: str = SCHEMA_VERSION
    record_id: RunId
    run_id: RunId
    plan_id: RunId
    attempt: int = Field(default=1, ge=1)
    state: TableState

    table_ref: TableRef
    source_location: str | None = None
    source_delta_version: int | None = Field(default=None, ge=0)

    decision: StrategyDecision
    strategy: Strategy
    warnings: list[StrategyWarning] = Field(default_factory=list)

    staging_location: str | None = None
    staging_glue_database: str | None = None
    staging_glue_table: str | None = None
    staged_snapshot_id: int | None = None
    staged_metadata_location: str | None = None

    production_location: str | None = None
    production_glue_database: str | None = None
    production_glue_table: str | None = None
    promoted_at: datetime | None = None
    approval_id: str | None = None

    delta_version_ledger: list[DeltaVersionEntry] = Field(
        default_factory=list, description="All versions still in the log (SPEC §6)"
    )
    unrecoverable_versions: list[int] = Field(
        default_factory=list, description="Vacuumed; reproducible by no strategy (SPEC §6)"
    )
    snapshot_map: list[SnapshotMapping] = Field(default_factory=list)
    history_effective_from_version: int | None = Field(default=None, ge=0)
    history_truncated: bool = False

    type_mappings: list[TypeMappingRecord] = Field(default_factory=list)
    timestamp_mode: TimestampMode = TimestampMode.TIMESTAMPTZ
    athena_constraints: list[str] = Field(
        default_factory=list, description="Recorded per table for timestamptz (Gate 0 #18, AT-21)"
    )
    partition_spec: list[PartitionColumn] = Field(default_factory=list)
    sort_order: list[str] = Field(default_factory=list)

    row_count_source: int | None = Field(default=None, ge=0)
    row_count_target: int | None = Field(default=None, ge=0)
    validation: ValidationResult | None = None
    column_aggregates: list[ColumnAggregate] = Field(
        default_factory=list, description="Data values — encrypted record only, never logged"
    )
    read_validation: list[EngineReadResult] = Field(default_factory=list)

    cdf: CdfDetail = Field(default_factory=CdfDetail)
    dlt: DltDetail = Field(default_factory=DltDetail)
    bridge: BridgeDetail = Field(default_factory=BridgeDetail)

    table_properties: dict[str, str] = Field(
        default_factory=dict, description="acc.source_table, acc.strategy, … (SPEC §7)"
    )
    uc_tags: dict[UntrustedText, UntrustedText] = Field(default_factory=dict)
    source_metadata: SourceMetadata = Field(default_factory=SourceMetadata)

    kms_key_arn: str | None = None
    evidence_uri: str | None = None
    cost: ActualCost = Field(default_factory=ActualCost)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    converted_at: datetime | None = None
    last_error: ErrorEnvelope | None = Field(default=None, description="Redacted (SPEC §9)")


# --------------------------------------------------------------------------- #
# Approval record (SPEC §9.1)
# --------------------------------------------------------------------------- #


class ApprovalRecord(_Base):
    """Promotion approval, shared with `gov-mcp`, `aws-mcp` and the Console.

    SPEC §9.1 is normative: `promote_table` succeeds only if the ledger holds a
    record with **all** of these fields, `decision = APPROVE`, `table_ref` equal,
    `plan_id` equal to the plan that staged the table, and `recon_record_id`
    referencing a `recon-mcp` record with `status = PASS` for the same table and
    staged snapshot id. Any mismatch → `APPROVAL_INVALID`; a missing or unknown
    `approval_id` → `APPROVAL_REQUIRED`.

    The JSON Schema rendering of this model is committed as
    `schemas/approval_record.json` and is the cross-service contract.
    """

    schema_version: str = SCHEMA_VERSION
    approval_id: RunId
    table_ref: TableFqn
    plan_id: RunId
    recon_record_id: RunId
    approver: str = Field(
        min_length=1, description="Console SSO identity or CLI IAM identity (SPEC §9.1)"
    )
    approved_at: datetime
    decision: ApprovalDecision


# --------------------------------------------------------------------------- #
# Tool inputs and outputs (SPEC §3)
# --------------------------------------------------------------------------- #


class ToolInput(_Base):
    """Every tool accepts `run_id` and emits spans tagged with it (SPEC §3)."""

    run_id: RunId


class DiscoverTablesInput(ToolInput):
    """`discover_tables(catalog, schema?, filter?)`."""

    catalog: Identifier
    schema_name: Identifier | None = Field(default=None, alias="schema")
    filter: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_*?%.-]{1,256}$",
        description=(
            "Table-name glob. Charset-constrained because it reaches a query over the "
            "Unity Catalog system tables; `discover.py` must still bind it as a "
            "parameter rather than interpolate it (SPEC §4)"
        ),
    )


class DiscoverTablesOutput(_Base):
    """SPEC §3: returns `DiscoveredTable[]`, plus the tables this version cannot
    name (§14 row 23) — reported, never silently dropped."""

    run_id: RunId
    catalog: str
    tables: list[DiscoveredTable] = Field(default_factory=list)
    table_count: int = Field(ge=0)
    unsupported: list[UnsupportedTable] = Field(
        default_factory=list, description="S7 UNSUPPORTED_IDENTIFIER; counted by assess-mcp"
    )


class ProfileTableInput(ToolInput):
    """`profile_table(table_ref)`."""

    table_ref: TableRef


class ProfileTableOutput(_Base):
    run_id: RunId
    profile: TableProfile


class RecommendStrategyInput(ToolInput):
    """`recommend_strategy(profile, options)` (SPEC §3, §14 row 20).

    `options` carries the decision-affecting settings — `history_days` /
    `history_versions` (S2), `timestamp_mode = "ntz_utc"` (forces S3),
    `relayout`, `register_bridge`, `cdf_window_days` — and defaults to the
    no-side-effect values of Gate 0 #1/#2/#5.
    """

    profile: TableProfile
    options: ConversionOptions = Field(default_factory=ConversionOptions)


class RecommendStrategyOutput(_Base):
    run_id: RunId
    table_ref: TableRef
    decision: StrategyDecision


class PlanConversionInput(ToolInput):
    """`plan_conversion(table_refs[], target, options)`."""

    table_refs: list[TableRef] = Field(min_length=1)
    target: ConversionTarget
    options: ConversionOptions = Field(default_factory=ConversionOptions)


class PlanConversionOutput(_Base):
    run_id: RunId
    plan: ConversionPlan


class ExecuteConversionInput(ToolInput):
    """`execute_conversion(plan_id, table_ref?, force=false)`."""

    plan_id: RunId
    table_ref: TableRef | None = Field(
        default=None, description="Restrict execution to one table of the plan"
    )
    force: bool = Field(
        default=False,
        description="Re-convert STAGED/VALIDATED after cleaning staging; "
        "refused for PROMOTED with ALREADY_PROMOTED (SPEC §3, §9)",
    )


class TableExecutionResult(_Base):
    """Per-table outcome of `execute_conversion`."""

    table_ref: TableRef
    state: TableState
    strategy: Strategy
    attempt: int = Field(default=1, ge=1)
    staged_snapshot_id: int | None = None
    staged_metadata_location: str | None = None
    staging_location: str | None = None
    validation: ValidationResult | None = None
    warnings: list[StrategyWarning] = Field(default_factory=list)
    record_pointer: str | None = Field(default=None, description="S3 URI of the conversion record")
    error: ErrorEnvelope | None = None


class ExecuteConversionOutput(_Base):
    run_id: RunId
    plan_id: RunId
    results: list[TableExecutionResult] = Field(default_factory=list)


class ValidateReadsInput(ToolInput):
    """`validate_reads(table_ref)`."""

    table_ref: TableRef


class ValidateReadsOutput(_Base):
    run_id: RunId
    table_ref: TableRef
    engines: list[EngineReadResult] = Field(default_factory=list)
    engines_agree: bool
    row_count: int | None = Field(default=None, ge=0)


class PromoteTableInput(ToolInput):
    """`promote_table(table_ref, approval_id)` — L1, human approval required."""

    table_ref: TableRef
    approval_id: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "Absent → APPROVAL_REQUIRED (SPEC §9.1, AT-13). Deliberately not "
            "pattern-constrained: a malformed id must reach `promote.py` and come "
            "back as APPROVAL_INVALID rather than as a schema error"
        ),
    )


class PromoteTableOutput(_Base):
    run_id: RunId
    table_ref: TableRef
    state: TableState
    approval_id: str
    production_location: str
    production_glue_database: str
    production_glue_table: str
    promoted_at: datetime
    record_pointer: str | None = None


class RollbackTableInput(ToolInput):
    """`rollback_table(table_ref)` — staging only; never touches source."""

    table_ref: TableRef


class RollbackTableOutput(_Base):
    run_id: RunId
    table_ref: TableRef
    state: Literal[TableState.ROLLED_BACK]
    staging_prefix_deleted: str | None = None
    glue_table_dropped: bool = False


class GetConversionRecordInput(ToolInput):
    """`get_conversion_record(table_ref)`."""

    table_ref: TableRef


class GetConversionRecordOutput(_Base):
    """Response of `get_conversion_record` (SPEC §3).

    The record is returned with `column_aggregates` **always empty**. SPEC §3
    says the tool returns the evidence record, while SPEC §8 and root rule 4
    make the aggregates data values that belong only in the SSE-KMS encrypted
    object in the client bucket — a tool response crosses into the agent's
    context and the span payload. Under root rule 1 the no-side-effect reading
    wins, and the stripping is enforced here rather than trusted to `ledger.py`,
    so no caller of this model can leak them. See OPEN_QUESTIONS #9.

    `validation.checksum_vector_hash` and the match flags survive, which is what
    an auditor needs from the response itself; the aggregates stay readable in
    the encrypted record at `record.evidence_uri`.
    """

    run_id: RunId
    record: ConversionRecord = Field(
        description="Evidence record with column aggregates stripped (SPEC §8)"
    )

    @model_validator(mode="after")
    def _strip_column_aggregates(self) -> GetConversionRecordOutput:
        if self.record.column_aggregates:
            self.record = self.record.model_copy(update={"column_aggregates": []})
        return self


def _export_json_schemas() -> None:
    """Regenerate the committed contracts in `schemas/`.

    Run as `uv run python -m table_mcp.schemas` after changing
    :class:`ApprovalRecord` or :class:`ConversionRecord`; the unit tests fail
    while the committed files are stale.
    """
    import json
    from pathlib import Path

    out_dir = Path(__file__).resolve().parents[2] / "schemas"
    for filename, model in (
        ("approval_record.json", ApprovalRecord),
        ("conversion_record.json", ConversionRecord),
    ):
        path = out_dir / filename
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        # Developer CLI, not server code: a file path we constructed, on stdout,
        # outside the logging chain. Nothing here can carry a data value.
        print(f"wrote {path}")  # noqa: T201


if __name__ == "__main__":
    _export_json_schemas()
