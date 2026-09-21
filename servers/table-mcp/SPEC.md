# `table-mcp` — Delta Lake → Apache Iceberg Conversion Service
## Build Specification v0.3.2 (Session 1 scaffold questions resolved 20 Sep 2026; ready for Session 2)

**Owner:** Lead architect · **Reviewers:** Senior engineer (WS-B), Security lead · **Status:** Draft for Gate 0
**Repo path:** `acc-migrate/servers/table-mcp/` · **Language:** Python 3.12, PySpark 3.5 on EMR Serverless, PyIceberg, delta-rs

This is a spec-first document. Claude Code builds to it; reviewers review against it; the acceptance tests in section 11 are the definition of done. Nothing in this document is optional unless marked *(v1.1)*.

---

## 1. Purpose

Convert Delta Lake tables governed by Unity Catalog into Apache Iceberg tables on the client's S3, registered in Glue Data Catalog, with history preserved where the formats allow, readable from Athena, Redshift (native Iceberg read, Spectrum fallback) and EMR Spark, and reconciled before promotion. Run entirely inside the client's AWS account, read-only against Databricks.

**Not in scope:** Snowflake sources; streaming tables with live writers (must be paused); Delta tables on non-S3 storage; MLflow feature tables; Iceberg → Delta reverse *(v2)*.

---

## 2. Design principles (inherited from the platform)

1. Read-only against source. The service holds no write permission on Databricks, Unity Catalog or the source S3 prefixes.
2. Deterministic. Same input, same strategy, same output. No LLM in the conversion path; agents may call this service, never replace it.
3. Idempotent and resumable. Every run has a manifest; re-running converges rather than duplicating.
4. Staging then promotion. Conversion writes to a staging catalog/database. Promotion to the production path is a separate, human-approved call.
5. Evidence-grade. Every table produces a conversion record (strategy, snapshots mapped, row counts, checksums, warnings) written to the execution ledger.

---

## 3. MCP interface

Server name: `table-mcp`. Transport: streamable HTTP via AgentCore Gateway; also runnable locally over stdio for Claude Code. All tools are typed with JSON Schema (Pydantic models in `schemas.py`). Errors return structured `ErrorEnvelope {code, message, retryable, table, hint}`.

| Tool | Purpose | Autonomy |
|---|---|---|
| `discover_tables(catalog, schema?, filter?)` | List Delta tables in scope via Unity Catalog system tables; returns `DiscoveredTable[]` = a frozen `TableRef` identity (`catalog`, `schema`, `name`) plus discovery attributes (location, format details, size, last modified, managed/external, DLT-managed flag). Every other table-scoped tool takes the bare `TableRef`; the two types are distinct so no tool can receive a half-populated ref | Read-only |
| `profile_table(table_ref)` | Deep inspection of the Delta log: protocol versions, table features (deletion vectors, column mapping, CDF, liquid clustering, generated columns, constraints, identity columns), partition scheme, schema history, version count and span, active file count, tombstones | Read-only |
| `recommend_strategy(profile, options)` | Returns `StrategyDecision {strategy, rationale[], warnings[], estimated_duration, estimated_cost}` per section 5. `options` carries the decision-affecting settings (`history_days`/`history_versions`, `timestamp_mode`, `relayout`, `register_bridge`, `cdf_window_days`) and defaults to the no-side-effect values (no history, no re-layout, no bridge) | Pure function |
| `plan_conversion(table_refs[], target, options)` | Produces a `ConversionPlan` — per-table strategy, ordering, parallelism, staging locations, estimated totals; no side effects | Pure function |
| `execute_conversion(plan_id, table_ref?, force=false)` | Runs the plan (or one table of it) into staging; writes conversion records; resumable. `force=true` re-converts a table in `STAGED`/`VALIDATED` after cleaning its staging output; **refused with `ALREADY_PROMOTED` for `PROMOTED` tables** (rollback of a promoted table is a separate, approved operation in v1.1). For S6 tables: with `options.register_bridge=true` registers the Glue bridge and sets state `FEDERATED`; otherwise records the decision and sets state `SKIPPED_S6` with no side effects | L2 — staging only |
| `validate_reads(table_ref)` | Confirms the staged Iceberg table reads from Athena, Redshift (native Glue-mounted Iceberg read; Spectrum external schema as fallback) and EMR Spark; returns row count and schema from each engine | Read-only on target |
| `promote_table(table_ref, approval_id)` | Moves the staged table to the production database/prefix; validates the approval record per §9.1. Missing/unknown `approval_id` → `APPROVAL_REQUIRED`; record present but any field mismatch → `APPROVAL_INVALID` | L1 — human approval required |
| `rollback_table(table_ref)` | Removes the staged table and its metadata; never touches source | L2 |
| `get_conversion_record(table_ref)` | Returns the evidence record with `column_aggregates` **always stripped** (enforced on the output model), leaving `validation.checksum_vector_hash` and the match flags. Aggregates are data values and must never reach an agent context or a span payload | Read-only |

All tools accept `run_id` and emit OpenTelemetry spans tagged with `run_id`, `table_ref`, `strategy`.

---

## 4. Inputs and connectivity

**Databricks access**
- Service principal, OAuth M2M, secret in client Secrets Manager. Grants: `USE CATALOG`, `USE SCHEMA`, `SELECT` on in-scope tables, `SELECT` on `system.information_schema`, `system.access.table_lineage`, `system.storage.*`. No write grants of any kind; startup self-check asserts this and fails fast if any write grant is present.
- Data files are read **directly from S3** via the Delta log (delta-rs / Delta Kernel), not through Databricks compute. This keeps Databricks DBU cost at **zero in the data path**. Discovery of Unity Catalog system tables requires a SQL warehouse: use the smallest serverless warehouse with 5-minute auto-stop; the small, bounded DBU cost is recorded in the run manifest. Additional read grants: Pipelines REST API (`pipelines:read`, to check DLT pause state) and Jobs API read. The tool needs `s3:GetObject` and `s3:ListBucket` on the source prefixes.
- Fallback *(v1.1)*: read via Databricks SQL warehouse for tables whose storage credentials cannot be granted to the AWS role.

**Target**
- Staging: `s3://{client-bucket}/iceberg/staging/{catalog}/{schema}/{table}/`, Glue database `{schema}__staging`.
- Production: `s3://{client-bucket}/iceberg/{catalog}/{schema}/{table}/`, Glue database `{schema}`.
- All writes with SSE-KMS using a client CMK passed in `options.kms_key_arn`. Refuse to run if absent.

**Precondition check** (`execute_conversion` refuses otherwise): no active writers on the table in the last N minutes (configurable, default 30) as evidenced by Delta log; DLT pipelines targeting the table are paused; source table is not a streaming table with continuous mode.

---

## 5. Strategy matrix

The core intellectual property of this server. `recommend_strategy` is a pure, tested function over the `TableProfile`.

| # | Strategy | When chosen | Mechanism | History |
|---|---|---|---|---|
| S1 | **Metadata-only snapshot** | Parquet files unmodified by Delta features; no deletion vectors; no column mapping, or `name` mode with an Iceberg name mapping (`schema.name-mapping.default`) generated from the Delta schema metadata; **identity partitions only** (generated/transformed partition columns → S3 in v1); files on S3 | Iceberg `snapshot`/`add_files` semantics via PyIceberg: register existing Parquet files as an Iceberg table with a single snapshot. Zero data copy. | Current version only; prior versions recorded as metadata in the conversion record (`version → timestamp → file set hash`), not as Iceberg snapshots |
| S2 | **Metadata replay** | As S1, **and** the client has explicitly requested history (`options.history_versions` or `options.history_days`; default **null** = no history) | Replay Delta log versions oldest→newest within the window as Iceberg snapshots using `add_files`/`delete_files` per version, tagging each snapshot with the Delta version and commit timestamp. Zero data copy. **Vacuumed versions cannot be replayed**: the window is truncated to the oldest fully-present version and the truncation is recorded (§6). | Iceberg snapshots for the window; older versions as metadata record |
| S3 | **Rewrite (compacting copy)** | Deletion vectors present; column mapping `id` mode; generated columns; identity columns; **any partition scheme that is not identity** (generated partition columns are rewritten with the equivalent Iceberg transform, e.g. `year(ts)`); tiny-file pathology (**>10,000 files AND median file size <8 MB**); client requests re-layout (Z-order/liquid → Iceberg sort order); `options.timestamp_mode = "ntz_utc"` (timestamp normalisation requires rewrite) | Spark job on EMR Serverless: read Delta at latest version with delta-rs/Spark, write Iceberg v2 with target file size and sort order; optional partition-spec redesign | Current version only, plus metadata record. Optional *(v1.1)*: replay of N prior versions by rewrite |
| S4 | **Rewrite with CDF preservation** | Tables with Change Data Feed enabled **and** downstream CDF consumers identified via lineage | As S3, then materialise the CDF window into a companion Iceberg changelog table `{table}__changes` with the same schema plus `_change_type`, `_commit_version`, `_commit_timestamp` | Change history for the window preserved as data |
| S5 | **DLT-managed table** | `TableProfile.dlt_managed == true` | Treat as S1/S3 by profile, **plus** flag to `jobs-mcp` that the producing pipeline must be migrated before promotion, and record DLT expectations for translation. Never promote a DLT table whose pipeline is still writing. | As underlying strategy |
| S6 | **External Iceberg already (UniForm)** | Delta table has UniForm Iceberg metadata enabled | Do not convert. Register the existing Iceberg metadata location in Glue as a **read-only bridge** and mark table as "federate now, convert at cut-over" with S1/S3 as the eventual strategy | n/a |
| S7 | **Unsupported — manual** | Protocol features not handled (e.g. row tracking with downstream dependency, type widening not representable, Delta variant type), or corrupted log | Return `StrategyDecision.strategy = MANUAL` with a precise reason; table goes to the manual queue | n/a |

**Decision order:** S6 → S7 → S5 (as modifier) → S4 → S3 → S2 → S1. First match wins; rationale lists every rule evaluated.

**Named warnings (in `StrategyDecision.warnings`, each with a stable code):** `HISTORY_NOT_PRESERVED` when history was requested but S3/S4 was chosen (deletion vectors, id column mapping, etc.); `HISTORY_TRUNCATED` when S2's window was cut at a vacuumed version; `TYPE_WIDENED`, `LENGTH_CONSTRAINT_DROPPED`, `SORT_ORDER_ADVISORY`. Warnings are copied into the conversion record and the client-facing report.

**S4 changelog window:** `options.cdf_window_days` (default **30**, independent of history options); if the Delta CDF retention is shorter, the window is truncated and `CDF_WINDOW_TRUNCATED` is emitted. S4 is chosen only when CDF is enabled **and** lineage shows a `table_changes()` consumer; CDF-enabled tables with no consumer route to S3/S1 with warning `CDF_UNUSED_DROPPED`.

**Type mapping (exhaustive; each row has `test_type_map_<delta_type>`):**

| Delta | Iceberg | Note |
|---|---|---|
| `BYTE`, `SHORT`, `INT` | `int` | Widening for BYTE/SHORT; recorded in conversion record as `type_widened` |
| `LONG` | `long` | |
| `FLOAT` | `float` | |
| `DOUBLE` | `double` | |
| `DECIMAL(p,s)` | `decimal(p,s)` | |
| `BOOLEAN` | `boolean` | |
| `STRING`, `CHAR(n)`, `VARCHAR(n)` | `string` | Length constraint dropped; recorded |
| `BINARY` | `binary` | |
| `DATE` | `date` | |
| `TIMESTAMP` | `timestamptz` (default) | Delta `TIMESTAMP` has instant semantics, so `timestamptz` is the faithful mapping. Athena can query `timestamptz` Iceberg columns (only Athena's own DDL is restricted to `timestamp`), and `table-mcp` registers via Glue, never Athena DDL. Two Athena constraints are recorded per table: millisecond precision on reads, and no cast from `timestamptz` to `timestamp`. Clients with Athena-first consumers may set `options.timestamp_mode = "ntz_utc"` to map to `timestamp` normalised to UTC (rewrite required → forces S3); the choice is recorded as `TIMESTAMP_MODE` in the record |
| `TIMESTAMP_NTZ` | `timestamp` | |
| `ARRAY<T>`, `MAP<K,V>`, `STRUCT<...>` | `list`, `map`, `struct` | Recursive |
| `INTERVAL` | — | **S7** (no Iceberg equivalent) |
| `VARIANT` | — | **S7** in v1; `variant` when Iceberg V3 lands in Athena/Redshift *(v1.1)* |
| `VOID`/`NULL` | — | **S7** with reason `void_column` |

**Partitioning:** identity partitions map directly (S1/S2 eligible). Generated partition columns (`year(ts)`, `date_trunc`, etc.) always route to S3 in v1, where the equivalent Iceberg transform is applied and the generated column is dropped from the output schema; S1 for transformed partitions is *(v1.1)*, pending `add_files` support for non-identity specs. Liquid clustering → Iceberg sort order on the same columns (advisory; documented in record).

---

## 6. History and time-travel handling

Delta versions and Iceberg snapshots are not equivalent. The service is explicit about what is preserved:

- Every conversion record contains the full Delta version ledger: `{version, timestamp, operation, operationParameters, file_set_hash}` for all versions still in the log, so an auditor can prove which state was migrated.
- S2 reproduces a bounded window as real Iceberg snapshots, tagged `delta_version=N`. Time-travel queries by version are documented as `FOR VERSION AS OF <iceberg_snapshot_id>` with a mapping table published alongside.
- Vacuumed Delta versions (files gone) cannot be reproduced by any strategy; the record marks them `unrecoverable`, S2 truncates its window to the oldest fully-present version, and the client-facing report states the effective retention boundary. There is no per-version rewrite fallback in v1.
- For regulatory-retention tables, the client is offered S2 with `history_days` matching their retention policy, costed by `plan_conversion`.

---

## 7. Glue Data Catalog registration

- Staging and production tables registered as Iceberg tables (`table_type = ICEBERG`, `metadata_location` set). Column comments and Unity Catalog table/column comments carried across as Glue parameters.
- Unity Catalog tags exported to Glue table parameters `uc_tag:{key}` and, when `gov-mcp` is present, converted to LF-Tags by that service (this server does not apply Lake Formation permissions).
- Table properties recorded: `acc.source_table`, `acc.source_delta_version`, `acc.strategy`, `acc.run_id`, `acc.converted_at`.

---

## 8. Validation

`execute_conversion` runs an inline validation before marking a table `STAGED`:
- Row count: source (Delta at pinned version) vs Iceberg staging — must match exactly.
- Schema equivalence after type mapping.
- Column-level aggregate checksum on up to 20 columns selected deterministically: all partition columns first, then primary/unique-key columns from Delta constraints, then remaining columns in schema order (sum/count-distinct/min/max as appropriate) — must match within configured tolerance (default 0 for exact types, 1e-9 relative for floating point). **Aggregates are data values**: they are written only to the encrypted conversion record in the client bucket, never to logs; logs carry match/mismatch and a hash of the aggregate vector.
- Partition count and distribution comparison.
- Full reconciliation (row hashes, sampled diffs) is `recon-mcp`'s job and is required before `promote_table` accepts an approval.

`validate_reads` executes `SELECT COUNT(*)` and schema introspection via Athena (boto3), Redshift via Data API (native Glue-mounted Iceberg read first, Spectrum external schema as fallback; the path used is recorded) and EMR Spark; all three must agree.

---

## 9. Failure handling, idempotency, concurrency

- Run manifest in DynamoDB `acc_migrate_runs`: `run_id, plan_id, table_ref, state ∈ {PLANNED, RUNNING, STAGED, VALIDATED, PROMOTED, FAILED, ROLLED_BACK, FEDERATED, SKIPPED_S6, MANUAL}, attempt, strategy, heartbeat_at, lease_expires_at, emr_application_id, emr_job_run_id, staged_snapshot_id, staged_metadata_location, last_error (redacted), record_pointer`.
- Re-running a `FAILED` table cleans partial staging output and restarts that table only; `STAGED`/`VALIDATED` are skipped unless `force=true`; `PROMOTED` is never re-converted by `execute_conversion` (`ALREADY_PROMOTED`).
- **Stale `RUNNING`:** every worker writes a heartbeat to the manifest every 60 s. A table in `RUNNING` whose heartbeat is older than the lease TTL (default 30 min) is treated as `FAILED` on the next run. Recovery order is strict: (1) if `emr_job_run_id` is set, call `emr-serverless:CancelJobRun` and wait for a terminal state (timeout 10 min → `RECOVERY_BLOCKED`, human required); (2) drop the staging Glue table if present; (3) delete the attempt's staging prefix; (4) restart. Spark jobs also receive the `run_id`/`attempt` and write only under an attempt-scoped prefix, so a late orphan can never commit into a newer attempt's location. The four commit points (S3 data files → Iceberg metadata → Glue table → manifest) are ordered so that cleanup is always a staging-prefix delete plus Glue table drop; nothing earlier in the order is authoritative until the manifest says `STAGED`.
- Per-table lock: DynamoDB conditional write with lease TTL (same 30 min) refreshed by the heartbeat; a crashed worker's lock expires. Second concurrent run is refused with `LOCKED` while the lease is live.
- **Staging/source disjointness:** startup asserts that every configured staging or production prefix is disjoint from every discovered source location; overlap is a hard stop.

### 9.1 Promotion gate (normative)
`promote_table(table_ref, approval_id)` succeeds only if the ledger holds an approval record with all of: `approval_id`; `table_ref` equal; `plan_id` equal to the plan that staged the table; `recon_record_id` referencing a `recon-mcp` record with `status = PASS` for the same `table_ref` and staged snapshot id; `approver` (identity from Console SSO or CLI IAM identity); `approved_at`; and `decision = APPROVE`. Any mismatch → `APPROVAL_INVALID`. The approval record schema lives in `schemas/approval_record.json` and is shared with `gov-mcp`, `aws-mcp` and the Console.
- Parallelism configurable; default 8 tables concurrently, EMR Serverless application shared per run with max capacity from `options`.
- All S3 writes to staging use a deterministic prefix per `plan_id`; rollback is a prefix delete plus Glue table drop.
- Source is never modified; if any code path would acquire a Databricks write, the startup self-check makes this a hard failure.

---

## 10. Security, logging, evidence

- IAM policy shipped as Terraform module `modules/table-mcp-role` (**module design approved by a human at Session 5 before any Terraform is written**, per root rules): `s3:GetObject/ListBucket` on source prefixes; `s3:*Object` on `iceberg/staging/*`, `iceberg/*` and `acc-migrate/evidence/*` of the client bucket; `glue:*Table/*Database` on the named databases; `kms:Encrypt/Decrypt/GenerateDataKey` on the client CMK; `emr-serverless:StartJobRun/GetJobRun/CancelJobRun/ListJobRuns` on the named application plus `iam:PassRole` for the job execution role; `iam:SimulatePrincipalPolicy` on its own role ARN (self-check); `athena:StartQueryExecution/GetQueryExecution/GetQueryResults` on the named workgroup and `s3:*Object` on the Athena results prefix `acc-migrate/athena-results/*`; `redshift-data:ExecuteStatement/DescribeStatement/GetStatementResult` and `redshift-serverless:GetCredentials` on the named workgroup; `dynamodb:*Item/Query/UpdateItem` on the run table; `secretsmanager:GetSecretValue` on the one Databricks secret; `kms:*` as above. Nothing else. Checkov-clean. Every resource is a named ARN; no wildcards.
- **Mechanical no-write gate (root rule 2 is no longer review-only).** CI fails on: a semgrep ruleset banning `write_deltalake`, `DeltaTable.merge/update/delete/vacuum/restore`, `.write.`/`.writeTo(` where the target resolves to a source URI, and any Databricks SQL execution outside `discover.py`/`profile.py`; plus `import-linter` contracts asserting that no module except `discover.py` and `profile.py` may import the Databricks SQL client, and that `convert/`, `promote.py` and `glue.py` may not import `deltalake` write APIs. Rules live in `policies/nowrite.semgrep.yml` and `.importlinter`, with tests proving each fires.
- **KMS enforcement (three layers, replaces the literal "one write helper" rule):** (1) `execute_conversion` refuses without `options.kms_key_arn`; (2) the ARN is injected into Spark (`fs.s3a.server-side-encryption*`) and PyIceberg FileIO (`s3.sse.*`) configuration at job start, so both libraries write SSE-KMS natively; (3) the Terraform module attaches a bucket policy denying `s3:PutObject` without `aws:kms` on the staging and production prefixes. `storage.py` holds the config builders and the precondition, not a wrapper around every write. Recorded as `docs/adr/ADR-0001-kms-enforcement.md` at repo root (all ADRs live under `docs/adr/`).
- **Redaction layer (`redact.py`):** all log emission passes through it. Partition paths are logged with partition *values* replaced by a stable hash (`trade_date=<h:8f3a>`); exceptions from PySpark, delta-rs, PyIceberg and Pydantic are wrapped in `ErrorEnvelope` with the library message scrubbed of quoted literals and path values before logging; Pydantic validation errors report field names only. No table data in logs. Logs carry counts, hashes, redacted paths, durations, and warnings.
- **Untrusted source text (§7 Glue parameters, `StrategyDecision.rationale`, any agent-visible field).** UC comments, tags, `constraints` and `generated_expression` are attacker-influencable. Before any such string reaches Glue, a log, a record or a prompt it is passed through `sanitize_source_text()`: strip all control characters and zero-width code points, normalise to NFC, cap at 1,024 characters (truncation marked), and wrap in the marker `<x-untrusted src="uc:{field}">…</x-untrusted>` wherever it can reach a model context. Rationale strings composed by `strategy.py` are template + enum only; no source text is interpolated into them — source text is carried in a separate `source_metadata` field that agents are instructed to treat as data.
- **Startup self-check scope:** (a) Databricks: resolve effective privileges for the service principal including group inheritance, ownership and catalog/schema-level grants via `information_schema.*_privileges` and `system.access` — any `MODIFY`, `CREATE*`, `WRITE*`, `MANAGE` or ownership on in-scope securables is a hard stop; (b) AWS: `iam:SimulatePrincipalPolicy` for `s3:PutObject`/`DeleteObject` on every discovered source prefix must return a deny (`implicitDeny` or `explicitDeny`); `allowed` is a hard stop; (c) staging/source prefix disjointness.
- **Auditor path for aggregates.** The full record including `column_aggregates` exists only in the encrypted evidence object in the client bucket. It is read by `acc-migrate evidence show --table <ref> --include-aggregates`, a CLI command that requires a separate IAM permission (`s3:GetObject` on the evidence prefix granted to an auditor role, not to the server role) and writes to the operator's terminal only. There is no MCP tool, no agent path and no log path to aggregates.
- Conversion record (JSON, one per table) written to `s3://{client-bucket}/acc-migrate/evidence/{run_id}/{table}.json` and referenced from the ledger. Schema in `schemas/conversion_record.json`.
- OpenTelemetry spans for each tool call and each strategy step; exported to CloudWatch via AgentCore Observability.

---

## 11. Acceptance tests (definition of done)

Fixtures are created in the sandbox Databricks workspace by `tools/fsi-fixtures` (its SPEC §3.1 names every table below). **Expected results** — row counts, aggregate-checksum vectors, Delta version ledgers, per-engine schemas — are recorded **once** by `fsi-fixtures snapshot-golden` from the live estate into `servers/table-mcp/tests/fixtures/expected/<fixture>.json`, committed in a reviewer-approved PR, and never regenerated by `table-mcp` code. Expected **strategy** and **type** decisions are human-authored from the §5 tables and live in `tests/fixtures/expected/strategy.yaml` and `types.yaml`; those unit tests need no live estate. Integration/acceptance tests are skipped until the `expected/` files exist.

| ID | Fixture | Expected strategy | Pass criteria |
|---|---|---|---|
| AT-01 | `trades_plain` — 200M rows, identity partition by `trade_date`, no features | S1 | Zero data copy; row count and checksums match; Athena/Redshift/EMR agree; < 5 min |
| AT-02 | `positions_history` — 50 versions over 90 days, `history_days=60` | S2 | ≥ 40 Iceberg snapshots tagged with Delta versions; time-travel to 3 sampled versions matches Delta `VERSION AS OF` |
| AT-03 | `customers_dv` — deletion vectors enabled, 5% soft-deleted | S3 | Row count equals Delta logical count (deleted rows excluded); checksums match |
| AT-04 | `ref_columns_idmap` — column mapping `id` mode, renamed and dropped columns in history | S3 | Final schema matches; renamed columns carry current names; record lists schema evolution |
| AT-05 | `orders_cdf` (physical table `meridian_fin.gl.journal_cdf`) — CDF enabled, consumer identified in lineage | S4 | `{table}__changes` (`journal_cdf__changes`) exists with `_change_type` populated for window; consumer flagged in record |
| AT-06 | `dlt_gold_risk` — DLT-managed, pipeline active | S5 (S1 underlying) | `execute_conversion` refuses while pipeline active; succeeds after pause; record flags pipeline for `jobs-mcp` |
| AT-07 | `mkt_data_uniform` — UniForm enabled | S6 | Not converted; Glue bridge table reads in Athena; record marks eventual strategy |
| AT-08 | `events_variant` — column of type VARIANT | S7 | `MANUAL` with precise reason; no side effects |
| AT-09 | `tiny_files` — 40k files, median 1.5 MB | S3 | Output file count < 400; checksums match |
| AT-17 | Stale `RUNNING` — kill worker mid-conversion, wait past lease TTL, re-run | — | Treated as FAILED; staging cleaned; converges; lock re-acquired |
| AT-18 | Redaction — force a PySpark exception containing a literal value | — | Logged `ErrorEnvelope` contains no quoted literals or partition values |
| AT-19 | Orphaned EMR job — kill orchestrator, leave Spark job running, recover | — | Recovery cancels the job run before cleanup; no Glue table or metadata from the orphan survives |
| AT-20 | `positions_history_dv` (fixture: copy of `positions_history` with deletion vectors enabled) with `history_days=60` | S3 | Warning `HISTORY_NOT_PRESERVED` present in decision and record |
| AT-21 | `trades_plain` (has `TIMESTAMP` column) read via Athena | S1 | `validate_reads` Athena leg succeeds on `timestamptz`; record notes millisecond precision |
| AT-22 | UniForm table without `register_bridge` | S6 | State `SKIPPED_S6`, zero side effects; with `register_bridge=true` → `FEDERATED` and Athena reads |
| AT-10 | `gen_partition` — partitioned by generated `year(ts)` column | S3 with `year(ts)` transform | Partition spec uses Iceberg transform; no generated column in output schema; `add_files` is never attempted |
| AT-11 | Idempotency — kill AT-01 at 50%, re-run | — | Converges; no duplicate files; single Glue table |
| AT-12 | Concurrency — same table from two runs | — | Second run refused with `LOCKED` |
| AT-13 | Promotion without approval id | — | `promote_table` refuses with `APPROVAL_REQUIRED` |
| AT-14 | Write-grant present on service principal | — | Server refuses to start; error names the grant |
| AT-15 | Missing KMS key | — | `execute_conversion` refuses before any S3 write |
| AT-16 | Estate test — all fixtures via `plan_conversion` + `execute_conversion` | Mixed | Full internal dataset (≥ 1 TB) staged, validated and read-checked in one run; total duration and cost recorded for the TCO model |

**Test naming:** one test per strategy (`test_strategy_rule_S1` … `S7`) asserting the decision, **plus** one per trigger condition (`test_strategy_rule_S3_deletion_vectors`, `test_strategy_rule_S3_id_column_mapping`, …) and one per decision-order boundary (`test_strategy_order_S6_beats_S1`, …).

Unit coverage on `strategy.py`, `types.py`, `partitioning.py` ≥ 90%; overall ≥ 80%. All CI security gates green.

---

## 12. Non-functional targets

- Throughput: S1 ≥ 500 tables/hour on metadata; S3 ≥ 1 TB/hour at 64 vCPU EMR Serverless.
- Cost visibility: `plan_conversion` estimates EMR vCPU-hours and S3 requests; `execute_conversion` records actuals for the learning loop.
- Cold start to first table under 3 minutes.
- Zero Databricks DBU consumption in the data path (discovery uses a minimal auto-stop SQL warehouse).

---

## 13. Repo layout and Claude Code instructions

```
servers/table-mcp/
  SPEC.md                    ← this document
  CLAUDE.md                  ← server-specific rules (below)
  pyproject.toml             ← uv-managed; pinned: pyiceberg, deltalake, pyspark, boto3, pydantic, opentelemetry
  src/table_mcp/
    server.py                ← MCP tool registration only; no logic
    schemas.py               ← Pydantic models for every input/output
    discover.py  profile.py  strategy.py  types.py  partitioning.py
    convert/ {__init__.py ← execute_conversion / rollback_table orchestration + COMMIT_ORDER, s1_snapshot.py, s2_replay.py, s3_rewrite.py, s4_cdf.py, s6_bridge.py}
    glue.py  validate.py  promote.py  ledger.py  locks.py  telemetry.py  storage.py  redact.py  selfcheck.py  errors.py  sanitize.py
  schemas/ {conversion_record.json, approval_record.json}
  OPEN_QUESTIONS.md            ← ADRs live at repo root: docs/adr/ADR-0001-kms-enforcement.md
  spark_jobs/ rewrite_job.py cdf_job.py
  policies/ nowrite.semgrep.yml   .importlinter
  tools/check_log_calls.py
  terraform/ modules/table-mcp-role, modules/table-mcp-emr
  tests/ unit/ integration/ fixtures/ acceptance/
```

**Server CLAUDE.md (extract):**
- Build strictly to `SPEC.md`; if the spec is ambiguous, write the question into `OPEN_QUESTIONS.md` and implement the safer option (no side effects).
- Never add a code path that writes to Databricks or source S3 prefixes. Any PR touching `promote.py` or IAM Terraform needs two human reviewers.
- Every strategy rule in section 5 must have a corresponding unit test named `test_strategy_rule_<id>`.
- Golden fixtures are never generated from the code under test.
- Log counts and hashes only; never sample values.

---

## 14. Gate 0 decisions (resolved from Session 0 findings, 16 Sep 2026)

| # | Question | Decision |
|---|---|---|
| 1 | Default history window | **None.** History is opt-in via `options.history_days`/`history_versions`; default null so S1 remains the common case. AT-01 requires S1 with defaults. |
| 2 | S3 re-layout (partition redesign) default | **Opt-in**, recommended by `assess-mcp`; S3 preserves the source partition scheme unless `options.relayout` is set. |
| 3 | `validate_reads` on Redshift | Prefer Redshift native Iceberg read via Glue Data Catalog auto-mounted database; fall back to Spectrum external schema when unsupported. Detected at runtime; recorded. |
| 4 | Iceberg V3 for `variant`/`interval` | S7 in v1; tracked in `OPEN_QUESTIONS.md` with the Athena/Redshift V3 GA dates. |
| 5 | UniForm bridge (S6) as an assessment quick win | **Yes** — `assess-mcp` lists S6-eligible tables as "federate today" candidates; `table-mcp` registers bridges only on explicit request. |
| 6 | Zero-DBU claim | Restated as **zero DBU in the data path**; discovery uses a minimal serverless SQL warehouse with auto-stop; cost recorded per run. |
| 7 | KMS single-write-helper rule | Replaced by the three-layer enforcement in §10; ADR-0001. |
| 8 | Naming | `jobs-mcp` is the notebook/DLT → Glue/EMR server named in the build plan; added to the platform design tool layer. `storage.py`, `redact.py`, `selfcheck.py` added to layout. |
| 9 | Golden fixture ownership | `fsi-fixtures snapshot-golden` records expected results once into `tests/fixtures/expected/`; strategy/type oracles are human-authored YAML (§11). |
| 10 | Server CLAUDE.md / PROMPTS.md drift | Both updated to v0.3: three-layer KMS enforcement, AT-01…AT-22. |
| 11 | IAM completeness | §10 now lists Athena, Redshift Data API, EMR job-run and `iam:SimulatePrincipalPolicy` permissions. |
| 12 | Orphaned EMR job on recovery | Cancel job run first; attempt-scoped prefixes; manifest carries `emr_job_run_id`, `heartbeat_at`, `staged_snapshot_id` (§9, AT-19). |
| 13 | S6 semantics | `register_bridge` option; states `FEDERATED` / `SKIPPED_S6` (§3, AT-22). |
| 14 | History requested but S3/S4 chosen | Named warning `HISTORY_NOT_PRESERVED` (§5, AT-20). |
| 15 | S4 window | `options.cdf_window_days` default 30; consumer required (§5). |
| 16 | Approval error codes | `APPROVAL_REQUIRED` vs `APPROVAL_INVALID` (§3). |
| 17 | `force` on PROMOTED | Refused, `ALREADY_PROMOTED` (§3, §9). |
| 18 | Delta `TIMESTAMP` → `timestamptz` | Confirmed against Athena docs: queryable; only Athena DDL is restricted. Default kept; `timestamp_mode=ntz_utc` opt-in (§5, AT-21). |
| 20 | `recommend_strategy` signature (OQ#5) | Amended: takes `(profile, options)`; options default to no-side-effect values (§3). |
| 21 | `TableRef` vs discovery attributes (OQ#6) | **Split**: frozen `TableRef` identity for every table-scoped tool; `DiscoveredTable` = `TableRef` + attributes, returned only by `discover_tables` (§3). |
| 22 | Orchestration placement (OQ#7) | Confirmed: `convert/__init__.py` holds `execute_conversion`/`rollback_table` and `COMMIT_ORDER`; `promote.py` stays promotion-only (two-reviewer file). Added to §13. |
| 23 | Identifier charset (OQ#8) | Strict pattern retained; non-conforming UC identifiers are **S7 `UNSUPPORTED_IDENTIFIER`**, reported not dropped, counted by `assess-mcp`. Quoting support is v1.1 (§4). |
| 24 | Aggregates in `get_conversion_record` (OQ#9) | Confirmed stripped; auditor reads the encrypted evidence object via `acc-migrate evidence show --include-aggregates` under a separate auditor IAM role. No MCP/agent/log path (§3, §10). |
| 25 | `errors.py` (OQ#10) | Added to §13; spec-named codes keep their identity and never collapse into `INTERNAL`. |
| 26 | Untrusted source text (OQ#13) | `sanitize_source_text()`: control/zero-width strip, NFC, 1,024-char cap, `<x-untrusted>` marking; rationale strings are template+enum only, source text carried separately (§10). |
| 27 | Mechanical no-write gate (OQ#14) | semgrep ruleset + import-linter contracts in CI, with tests proving each fires (§10). |
| 28 | Delta `INTERVAL` (OQ#2) | Closed: no fixture uses it; remains S7 with reason `unsupported_type`; `assess-mcp` counts occurrences per estate so a client exception surfaces at assessment, not at conversion. |
| 19 | Wording | "data path" DBU claim; Redshift native read preferred with Spectrum fallback; deny may be implicit or explicit; deterministic 20-column selection; ADRs under `docs/adr/`. |
