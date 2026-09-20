# `assess-mcp` — Databricks Estate Assessment, TCO and Wave Planning Service
## Build Specification v0.1 (Gate 0 condition 6: stay / federate / exit modelled as first-class options)

**Owner:** Lead architect · **Product owner:** owns the report and the client-facing narrative · **Reviewers:** Senior engineer (WS-A), Finance/commercial lead (cost model), Security lead (data-handling statement)
**Repo path:** `acc-migrate/servers/assess-mcp/` · **Language:** Python 3.12, Polars, DuckDB, NetworkX, Databricks SDK, boto3, Jinja2, python-pptx, openpyxl
**Status:** Draft for Gate 0. The Assessment Agent (L3) is built on top of this server; the server itself is deterministic.

---

## 1. Purpose

Read a Databricks estate's **metadata and usage only** and produce, in under one working day, a defensible decision pack for a CDO/CFO: workload inventory, three-scenario TCO (**stay**, **federate**, **exit**), per-workload target recommendation, migration wave plan with effort and risk, and the governance/compliance exposure summary. The pack is designed to be honest enough that a client whose best option is to stay is told so.

**Not in scope:** reading any table contents; Snowflake (Phase B); code conversion estimates beyond complexity classification (that is `jobs-mcp`'s job); commercial pricing of ACC services (the estimator consumes this server's output).

---

## 2. Design principles

1. **Metadata-only, provably.** The service principal has no `SELECT` on any business table. Startup self-check asserts this. The data-handling statement is one page and true.
2. **Three scenarios, one model.** Stay, federate and exit are computed from the same inputs with the same assumptions engine, so the comparison is fair and auditable.
3. **Ranges, not points.** Every cost is a P10/P50/P90 with the driving assumptions listed. Point estimates are how vendor TCO decks lose trust.
4. **Deterministic.** Same snapshot, same pack. The Assessment Agent narrates and answers questions; it does not change numbers.
5. **Assumptions are data.** Pricing, rates, utilisation factors and mapping rules live in versioned YAML, never in code, so Finance can review them and each client's pack records exactly which version was used.

---

## 3. MCP interface

| Tool | Purpose | Autonomy |
|---|---|---|
| `collect_metadata(workspaces[], lookback_days=90)` | Snapshot system tables, workspace APIs and pricing into an immutable `AssessmentSnapshot`; returns id and hash | Read-only |
| `inventory(snapshot_id)` | Normalised inventory: tables, pipelines, jobs, notebooks, SQL warehouses, clusters, users, groups, policies | Pure function |
| `classify_workloads(snapshot_id)` | Assign every job/query stream to a workload class (§5) with confidence and evidence | Pure function |
| `build_dependency_graph(snapshot_id)` | Lineage + job dependency DAG; identifies domains and cut-points | Pure function |
| `model_scenarios(snapshot_id, assumptions_version, options)` | Compute stay / federate / exit TCO, 3-year and 5-year, P10/P50/P90 | Pure function |
| `recommend_targets(snapshot_id)` | Per workload: consumption engine (Redshift / Athena / EMR / Glue) with rationale | Pure function |
| `plan_waves(snapshot_id, constraints)` | Wave plan from dependency graph, risk, data classification, business calendar | Pure function |
| `governance_exposure(snapshot_id)` | Count and classify RLS/masks/ABAC/dynamic views; pre-compute expected gap ids by calling `gov-mcp` taxonomy rules on metadata | Pure function |
| `render_pack(snapshot_id, format)` | Decision pack (PPTX + XLSX + JSON + HTML); executive summary, scenario comparison, wave plan, appendices | Writes files |
| `explain(snapshot_id, question)` | Structured lookup for the Assessment Agent: returns the evidence rows behind any number | Read-only |

All tools accept `run_id`; spans tagged `run_id`, `snapshot_id`, `workspace_id`.

---

## 4. Inputs

**Databricks (read-only, metadata only)**
- `system.billing.usage` and `system.billing.list_prices`: DBUs by SKU, cluster, job, warehouse, user, per hour, for the lookback window.
- `system.compute.clusters`, `node_types`, `warehouses`: instance types, autoscaling settings, uptime.
- `system.query.history`: statement text (hashed and parsed for shape; never stored raw), duration, bytes scanned/produced, warehouse, user, client application.
- `system.access.table_lineage`, `column_lineage`, `audit`: consumers, producers, access frequency.
- `system.information_schema.*`: tables, columns, sizes (`table_storage`), formats, features, grants, policies, tags.
- Workspace APIs: jobs, pipelines (DLT), notebooks (metadata and import counts only — the notebook body is parsed for complexity signals, not stored), repos, SQL dashboards/alerts, Model Serving and MLflow presence (flagged, not assessed).
- Storage: S3 inventory or `system.storage.*` for physical bytes, file counts, small-file ratios.

**AWS (client account, read-only)**
- Current AWS spend on data services if any (Cost Explorer), region, existing Redshift/Glue/EMR footprint, Reserved/Savings Plan coverage.
- AWS Price List API snapshot for the target region, cached and versioned in `assumptions/pricing/aws-<region>-<date>.yaml`.

**Client-provided (YAML, reviewed by product owner)**
- Contract terms: Databricks commit remaining, discount tier, renewal date; AWS EDP/PPA terms.
- Business calendar: freeze windows, regulatory reporting dates.
- Constraints: onshore-only data classes, must-keep workloads (e.g. ML platform stays on Databricks), target engines allowed.

**Never collected:** row data, personal data beyond user identifiers already in audit tables, raw query text. Hashed query shapes only.

---

## 5. Workload classification

Each job, pipeline, warehouse query stream and notebook is classified from usage evidence:

| Class | Signals | Default exit target |
|---|---|---|
| **Batch ETL** | Scheduled jobs/DLT, high write ratio, predictable duration | EMR Serverless (Spark) for heavy; Glue 5.0 for light |
| **Interactive BI** | SQL warehouse, high concurrency, short queries, BI client user-agents, repeated shapes | Redshift Serverless |
| **Ad-hoc analytics** | Notebooks/SQL, low concurrency, bursty, exploratory shapes | Athena |
| **Streaming** | Continuous DLT / Structured Streaming | Flagged; v2 scope; may force *stay* or *federate* for that domain |
| **ML / feature engineering** | MLflow, Model Serving, feature tables, GPU node types | Flagged; default *stay* or SageMaker (v2); excluded from exit TCO unless client opts in |
| **Governance-heavy consumption** | Tables with RLS/masks and many consumers | Redshift (RLS/DDM support) with note on `gov-mcp` mechanism changes |

Confidence < 0.7 goes to a manual review list in the pack. Classification rules are in `rules/classify.yaml` with unit tests per rule.

---

## 6. Scenario model (the core)

All three scenarios share: same lookback-derived demand (compute hours, bytes scanned, storage), same growth assumptions (client-provided or default 15% p.a.), same horizon (3 and 5 years), same FX and discounting, same labour rates. Only the platform shape differs.

### 6.1 Stay (baseline)
- Databricks DBUs × list/committed price with contract discount and expected renewal uplift; cloud compute underneath (instance-hours) and storage on the client's S3.
- Optimisation-adjusted variant: what stay costs if the client applies known quick wins (serverless SQL, photon, auto-stop, cluster right-sizing) — so exit is not compared against an unoptimised strawman.
- Includes: platform admin FTEs, existing skills, zero migration cost, remaining commit obligations, renewal risk range.

### 6.2 Federate (stay on Databricks compute for writes; read from AWS-native engines via UniForm / Iceberg REST / Glue federation)
- Databricks costs for **producers** remain (ETL/DLT); **consumers** move to Athena/Redshift where lineage shows read-only access.
- Adds: Glue Data Catalog federation, Athena/Redshift Spectrum scan costs, UniForm enablement effort, dual-governance operating cost (Unity Catalog + Lake Formation).
- Removes: SQL warehouse DBUs for migrated consumers.
- Explicitly models **governance duplication risk**: RLS/masks must exist on both sides; `governance_exposure` output drives an operating-cost adder and a risk flag.
- Realistic for: estates where BI/ad-hoc DBU spend dominates and ETL is entangled or ML-heavy.

### 6.3 Exit (full migration to S3 + Iceberg + Glue + Lake Formation; Redshift / Athena / EMR / Glue consumption)
- Per-workload target from `recommend_targets`; cost from mapped compute (EMR vCPU-hours, Glue DPU-hours, Redshift RPU-hours, Athena TB scanned) using utilisation factors from `assumptions/mapping.yaml` (e.g. Photon → EMR Spark 3.5 performance ratio range 0.8–1.3; SQL warehouse → Redshift Serverless RPU sizing rule).
- One-time migration cost: effort from wave plan × rates (ACC + client), parallel-run double-running cost by wave duration, tooling run cost (from `table-mcp`/`recon-mcp` recorded actuals), training.
- Ongoing: platform engineering FTE delta, Lake Formation operating cost, loss of Databricks-specific features (documented, not priced unless the client provides a value).
- Exit **excludes** flagged ML/streaming domains by default and shows them as *stay* residual so the CFO sees the true post-migration Databricks bill, not zero.

### 6.4 Output
- Table per scenario: Year 1–5 costs P10/P50/P90; cumulative; NPV at client discount rate; **crossover month** where exit's cumulative cost drops below stay/federate (or "no crossover in horizon").
- **Sensitivity tornado**: top 8 assumptions by impact on the exit-vs-stay delta (e.g. renewal uplift, Photon/EMR ratio, parallel-run length, growth, Redshift utilisation).
- **Recommendation logic** (rules in `rules/recommend.yaml`): if P50 exit saving < 15% or crossover > 30 months → recommend *stay-optimised* or *federate*; if governance duplication risk is high → discourage *federate*; else recommend *exit* with the wave plan. The recommendation always states the conditions under which it would flip.

---

## 7. Wave planning

Inputs: dependency graph, data classification, table/job sizes, governance exposure, business calendar, constraints.
Algorithm: community detection on the lineage graph → candidate domains; order by (low downstream fan-in, low governance exposure, low data sensitivity, high DBU saving) with regulatory-date avoidance; enforce that a table moves no earlier than all its producers; PII/PCI domains never in wave 1; ML/streaming excluded unless opted in.
Output per wave: objects, estimated effort (from `assumptions/effort.yaml` by object class and complexity), parallel-run duration, expected `table-mcp` strategies and `gov-mcp` gap ids, risk score, onshore-only flag (from data classes), suggested calendar slot.

---

## 8. Governance exposure

Runs `gov-mcp`'s gap-detection rules (imported as a library) over the metadata snapshot to pre-count expected gap ids per catalog: how many masks are value-transforming (G-CM-02), how many filters are session-dependent (G-RL-02), unmapped principals, ABAC policies. Surfaces the **federate** governance-duplication risk and the **exit** mechanism-change count in the executive summary, since these are the items that stall FSI programmes.

---

## 9. Decision pack contents

1. **Executive summary (1 page):** current annual spend, three-scenario 3-year P50 with ranges, crossover month, recommendation and its flip conditions, top 3 risks.
2. **Estate at a glance:** workloads by class, DBU by class, storage, growth, governance exposure counts.
3. **Scenario comparison:** tables, tornado, NPV, "what stays on Databricks regardless".
4. **Target architecture and per-workload mapping.**
5. **Wave plan:** Gantt, per-wave effort/risk/onshore flags, parallel-run windows.
6. **Governance and compliance exposure:** expected gap ids, regime flags, what the compliance pack will contain.
7. **Assumptions register:** every assumption with source, version and range.
8. **Data-handling statement:** what was read, what was not, retention.
9. **Appendices:** inventory, manual-review lists, low-confidence classifications.

Formats: PPTX (exec), XLSX (model with live assumptions sheet), JSON (machine), HTML (Console v1.1). Templates in `templates/`, branded neutrally (client logo slot, no vendor logos).

---

## 10. Security and evidence

- IAM/Databricks permissions: system tables and workspace read APIs only; **no `SELECT` on any catalog other than `system`**; self-check refuses to start otherwise. No `s3:GetObject` on data prefixes.
- Query text is hashed (xxhash64) and parsed for shape features immediately; raw text is never persisted. Notebook bodies are parsed in memory for complexity signals; not stored.
- Snapshot stored encrypted in the client account; retention default 90 days post-engagement (align with `gov-mcp` §13.6).
- Every pack embeds `snapshot_hash`, `assumptions_version`, `rules_version`, generator version, and is recorded in the ledger. Two packs from the same snapshot and versions are byte-identical except timestamps.

---

## 11. Acceptance tests (definition of done)

| ID | Fixture / input | Pass criteria |
|---|---|---|
| AT-A01 | Meridian full estate | `collect_metadata` completes < 2 h; zero `SELECT` on non-system catalogs in Databricks audit log |
| AT-A02 | Meridian | Classification: ≥ 85% of jobs/streams classified with confidence ≥ 0.7; every named fixture class (DLT pipelines → Batch ETL, BI warehouse stream → Interactive BI, notebooks → Ad-hoc) correct |
| AT-A03 | Meridian + synthetic contract YAML | Three scenarios produced with P10/P50/P90; stay-optimised ≤ stay; exit shows non-zero Databricks residual for ML fixture domain |
| AT-A04 | Sensitivity | Tornado lists renewal uplift and Photon/EMR ratio in top 5 for Meridian; changing each by ±20% moves the delta in the expected direction |
| AT-A05 | Recommendation flip | With commit discount raised to 45% and growth 5%, recommendation flips from exit to stay-optimised/federate and states the flip condition |
| AT-A06 | Federate governance risk | Meridian's 4 masks + 3 session filters produce a "high duplication risk" flag on federate |
| AT-A07 | Wave plan | `meridian_ref` in wave 1; `meridian_cust` never in wave 1; no table before its producers; regulatory-date windows avoided; onshore flag on PII/PCI waves |
| AT-A08 | Governance exposure | Expected gap ids match `gov-mcp` AT-G16 register within ±5% counts |
| AT-A09 | Determinism | Two runs, same snapshot/versions → identical JSON (excluding timestamps) |
| AT-A10 | Pack render | PPTX/XLSX/JSON/HTML generated; XLSX assumptions sheet edits recompute P50; no vendor logos; data-handling statement present |
| AT-A11 | Startup with `SELECT` on a business catalog | Server refuses to start |
| AT-A12 | Offline mode | Client-provided export of system tables (CSV/Parquet) produces the same pack as live mode |
| AT-A13 | TCO validation | For Meridian's simulated Databricks bill (generated from `system.billing.usage` fixture), model reproduces actual stay cost within ±5% |

Coverage ≥ 90% on `scenarios/`, `classify/`, `waves/`; ≥ 80% overall. Assumptions YAML validated by schema in CI.

---

## 12. Repo layout

```
servers/assess-mcp/
  SPEC.md CLAUDE.md OPEN_QUESTIONS.md pyproject.toml
  assumptions/ {pricing/, mapping.yaml, effort.yaml, rates.yaml, growth.yaml}   ← versioned, Finance-reviewed
  rules/ {classify.yaml, recommend.yaml}
  templates/ {exec.pptx.j2, model.xlsx.j2, pack.html.j2}
  src/assess_mcp/
    server.py schemas.py
    collect/ {system_tables.py, workspace_api.py, aws_pricing.py, offline_export.py}
    inventory.py classify/ graph.py
    scenarios/ {demand.py, stay.py, federate.py, exit.py, sensitivity.py, npv.py}
    targets.py waves/ governance_exposure.py
    render/ {pptx.py, xlsx.py, html.py, json.py}
    ledger.py telemetry.py errors.py
  tests/{unit,integration,acceptance,fixtures/expected}
  terraform/modules/assess-mcp-role
```

**Server CLAUDE.md (extract):** metadata only — never add `SELECT` on non-system catalogs or `s3:GetObject` on data prefixes; hash query text before any persistence; all numbers come from `assumptions/` and `rules/` YAML, never literals in code; stay, federate and exit must share `demand.py` — no scenario-specific demand tweaks; every recommendation must include flip conditions.

---

## 13. Open questions for Gate 0

1. Default growth assumption when the client provides none: 15% p.a. (proposed) vs. derive from the lookback trend.
2. Discount rate for NPV: client WACC if provided, else 8% (proposed).
3. Whether to price "loss of Databricks-specific features" (e.g. Photon, Genie, Unity Catalog lineage UI) via a client-provided value or leave qualitative (proposed).
4. Recommendation thresholds: 15% P50 saving and 30-month crossover (proposed) — Finance/commercial lead to confirm.
5. Offline mode as a first-class path for clients that refuse live connection at assessment stage (proposed yes; AT-A12).
6. Whether the pack should include ACC's indicative services price, or keep the pack vendor-neutral and price separately via the estimator (proposed separate).
