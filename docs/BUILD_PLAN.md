# Databricks → AWS-Native Migration Accelerator
## Build Plan — Data Practice, ACC
*(Snowflake source added in Phase B)*

**Owner:** Data Practice Lead · **Version:** 0.5 draft · **Date:** 16 Sep 2026 · **Classification:** Internal

---

## 0. Scope decisions (16 Sep 2026)

| Decision | Outcome |
|---|---|
| Source sequencing | **Databricks first (v1). Snowflake added as Phase B (v1.2).** Rationale: whitespace is deepest in Delta→Iceberg and Unity Catalog→Lake Formation; Snowflake SQL conversion is commoditised (SCT, SnowConvert-class tools) and slots in via the adapter contract without touching the agents. |
| Development model | AI-assisted, spec-first, built with Claude Code; humans own specs, tests, reviews and approvals. Enterprise release bar (section 6) enforced by CI. |
| Agentic platform | Approved on the thin-track path: MCP-native tools from day one, compliance policy core, Assessment Agent at L3 in v1; remaining agents decided at Gate 2 by clean-rate rule. See companion design document. |
| Delivery model | Hybrid India + UK/EU (section 8.1). |
| UI | No console in v1; polished generated artefacts. Migration Console is the first v1.1 deliverable. |
| Model gateway | Amazon Bedrock only, in client account/region. |

**Revised v1 envelope:** ~40–45 person-weeks, 11–12 weeks, four-person review-led team plus 0.2 security lead and the agentic-AI engineer (40% to Gate 1, then full-time). Phase B (Snowflake): ~6–8 weeks, +20–25 person-weeks. Sections below describe the full two-source stack; v1 delivers the Databricks path, and Snowflake items (WS-C, Snowflake extractors, Snowflake RBAC and Tasks) move to Phase B.

**Revised gates (v1):** Gate 0 week 2 · Gate 1 week 6 (Delta→Iceberg converts full internal dataset; UC governance extraction complete) · Gate 2 week 10 (end-to-end dry run, Assessment Agent live, Conversion Agent scope decided) · Gate 3 week 11–12 (v1 released, compliance pack approved, Databricks pilots booked).

**Named risk:** Databricks' "stay and federate" answer (UniForm + Glue Data Catalog federation). The TCO toolkit models this option honestly from day one.

---

## 1. Objective

Build a reusable, demonstrable accelerator stack that lets ACC scope, price and deliver Databricks and Snowflake exits to an AWS-native lakehouse (S3 + Iceberg + Glue Data Catalog, with Redshift / EMR Serverless / Athena as consumption layers) faster and with lower delivery risk than a bespoke engagement.

**What "done" looks like for v1 (end of Phase 2):**
- Assessment toolkit produces a before/after TCO and wave plan from a real Unity Catalog or Snowflake metadata export in under one working day.
- Delta → Iceberg utility converts a 1 TB+ internal dataset with history preserved and reconciles clean.
- Snowflake SQL → Redshift converter handles ≥80% of the internal benchmark query set without manual edits.
- Reconciliation harness runs end-to-end and produces a sign-off report.
- Reference architecture, runbook and a 20-minute demo exist and have been used in at least one client conversation.
- Every asset passes the enterprise-grade release bar in section 6 (security scan clean, ≥80% test coverage on conversion logic, IaC-deployable, audit logging on, documentation complete, architecture review board sign-off).
- Compliance pack (section 7) exists: data-handling statement, control mapping, third-party licence register, and an assessment questionnaire response a client's risk team can consume as-is.

**Out of scope for v1:** BI tool repointing (Tableau/Power BI semantic layers), ML platform migration (MLflow → SageMaker), streaming (Structured Streaming → Kinesis/MSK). Candidates for v2.

---

## 2. Planning assumptions

These need confirming at the kick-off. Everything downstream flexes with them.

| Assumption | Working value |
|---|---|
| Core build team | 1 lead architect, 3 senior data engineers, 1 mid-level engineer, 0.5 FTE product/GTM owner |
| Allocation | 60–80% bench time; expect interruptions from billable work |
| Duration to v1 | 16 weeks (4 phases) |
| Cloud budget | AWS sandbox account, ~USD 3–5k/month for test workloads; Databricks and Snowflake trial or existing internal accounts for source-side fixtures |
| Internal dataset | Existing internal data platform or a synthetic FSI-style dataset (transactions, customers, positions) at 1–5 TB |
| Partner alignment | AWS PSA/PDM engaged from week 2 for architecture review and possible ISV/credits support |

---

## 3. Phasing

Sequenced as per the original proposal: Snowflake → Redshift and Delta → Iceberg first, where bench strength is deepest and client risk is highest.

### Phase 0 — Mobilise (weeks 1–2)
- Confirm team, allocation and budget; stand up AWS sandbox with Lake Formation, Glue, Redshift Serverless, EMR Serverless, Athena, MWAA.
- Provision source fixtures: Databricks workspace with Unity Catalog and a Snowflake account, both loaded with the internal dataset. Include deliberately awkward cases (schema evolution, deletes, time-travel history, stored procedures, RLS policies, tags).
- Agree definition of done per asset (section 5), repo structure, coding standards, licence model (internal IP vs. open-sourceable components).
- Stand up the engineering baseline before any feature code: mono-repo with branch protection, CI (lint, unit, integration, SAST/secret scan, SBOM), IaC (Terraform) for every AWS resource, OIDC-based CI credentials — no long-lived keys.
- Sandbox guard-rails: AWS Organizations SCPs, CloudTrail + Config enabled, encryption-at-rest enforced (KMS CMKs), no public S3, budget alarms. Sandbox holds **synthetic data only** — no client or production data at any point in the build (see section 7).
- Security and Legal briefed; open the third-party licence review (Delta, Iceberg, Airflow, Great Expectations/Deequ are Apache-2.0; confirm Databricks and Snowflake terms of service permit use of trial/internal accounts for tooling development).
- Brief AWS partner team; request architecture review slot for week 8.

**Gate 0:** team on-boarded, environments live and passing guard-rail checks, CI pipeline green on an empty repo, licence review opened, benchmark query set (~150 Snowflake queries, ~30 Databricks notebooks/DLT pipelines) frozen.

### Phase 1 — Core assets (weeks 3–8)
Three parallel workstreams.

**WS-A · Assessment & TCO toolkit** (lead architect + 1 engineer)
- Metadata extractors: Unity Catalog system tables and Snowflake `ACCOUNT_USAGE` / `INFORMATION_SCHEMA` (query history, warehouse credits, table sizes, access patterns).
- Workload classifier: BI/interactive, batch ETL, ad-hoc, ML. Drives the consumption-layer recommendation (Redshift vs. Athena vs. EMR).
- Cost model: parameterised AWS pricing (Redshift Serverless RPU-hours, EMR Serverless vCPU/GB-hours, Athena TB scanned, Glue DPU-hours, S3) vs. observed source spend. Include a sensitivity range, not a point estimate.
- Wave planner: dependency graph from lineage/query history → suggested migration waves.
- Output: TCO deck template + wave plan spreadsheet, auto-populated.

**WS-B · Delta → Iceberg conversion utility** (2 senior engineers)
- Weeks 3–4: spike. Evaluate metadata-only conversion (Iceberg `snapshot`/`migrate` procedures, UniForm as an intermediate) vs. rewrite for each table pattern. Decide per-pattern strategy.
- Weeks 5–7: build. Handle: partition evolution, deletion vectors, column mapping, schema evolution history, time-travel (map Delta versions → Iceberg snapshots where possible, document where not), DLT-managed tables, external vs. managed.
- Week 8: register converted tables in Glue Data Catalog; validate reads from Athena, Redshift Spectrum and EMR Spark.
- Explicit positioning: what UniForm / Snowflake Iceberg tables already solve, and what this utility adds (full exit, history, DLT, non-UniForm tables).

**WS-C · Snowflake SQL → Redshift converter** (1 senior + 1 mid-level engineer)
- Evaluate AWS SCT and Amazon Q Developer transformation as the base; build ACC assets on the residual gap.
- Focus on: `QUALIFY`, `FLATTEN`/semi-structured `VARIANT`, `MERGE` semantics, stored procedures (Snowflake Scripting / JavaScript → Redshift PL/pgSQL), UDFs, time-zone and `TIMESTAMP_NTZ` handling, `CLONE` patterns → equivalent Redshift approaches.
- Coverage report: for each query in the benchmark set, converted clean / converted with warning / manual.
- Athena target as a secondary output (Trino SQL dialect) — lower priority in Phase 1.

**Gate 1 (week 8):** AWS Well-Architected review (Security, Reliability, Cost pillars); WS-B converts the full internal dataset; WS-C ≥70% clean coverage; WS-A produces a first TCO from the internal fixtures; internal architecture review board (ARB) sign-off on the target reference architecture; threat model for each asset drafted.

### Phase 2 — Completing the stack (weeks 9–13)

**WS-D · Reconciliation harness** (1 senior engineer, starts week 9)
- Row count, column-level checksums (hash aggregates), business aggregates by partition, sampled row-level diff.
- Runs on EMR Serverless or Glue; source connectors for Databricks SQL and Snowflake; target connectors for Athena/Redshift/Iceberg-on-S3.
- Tolerance configuration (floating point, timestamp precision), HTML/PDF sign-off report suitable for change-approval boards.

**WS-E · Governance mapping** (lead architect + 1 engineer)
- Extract Unity Catalog grants, row filters, column masks and tags; Snowflake roles, grants, RLS policies, masking policies, tags.
- Translate to Lake Formation permissions, LF-Tags, data filters (row/column), and Glue Data Catalog resource policies. Document the semantic gaps (e.g. dynamic masking behaviour differences) — FSI audit teams will ask.
- Output: mapping report + Terraform/CloudFormation that applies the target permissions.

**WS-F · Orchestration patterns** (mid-level engineer + WS-C engineer)
- Databricks Workflows JSON → Airflow DAG (MWAA) generator; Snowflake Tasks/Streams → Step Functions + EventBridge patterns.
- Pattern catalogue rather than a full converter: 8–10 documented, tested patterns cover most estates.

**WS-G · Databricks notebook / DLT → Glue / EMR Serverless templates** (WS-B engineers, after Gate 1)
- Parameterised PySpark job templates; `dbutils` and Databricks-specific API shims; DLT expectations → Great Expectations / Deequ on EMR; DLT materialised view semantics → scheduled incremental jobs.

**Gate 2 (week 13):** end-to-end dry run — assess → convert → migrate → reconcile — on the internal dataset, recorded as a demo; penetration test / security review of any component that touches source credentials; compliance pack in draft; DR/rollback procedure rehearsed once.

### Phase 3 — Harden, package, go to market (weeks 14–16)
- Runbook: cut-over playbook, parallel-run strategy, rollback, hypercare.
- Reference architecture diagrams and a one-page positioning per asset.
- Packaging: repo hygiene, README per asset, install scripts, licence decision applied, SBOM published per release, signed artefacts.
- Operational readiness: support model (L2 from build team, L3 from lead architect), SLA for fixes on client engagements, versioned release notes, deprecation policy, backlog triage cadence.
- Compliance pack finalised and approved (section 7).
- Sales enablement: 20-minute demo, client-facing TCO sample, estimator (T-shirt sizing by table count / query count / complexity), draft SOW language and rate card.
- AWS: submit for partner programme alignment (Migration Acceleration Program eligibility, Data & Analytics competency evidence), request co-marketing/credits.
- Identify pilot clients: one Indian FSI and one UK/EU FSI, so both delivery tiers are exercised in Q1.

**Gate 3 (week 16):** v1 tagged and released under semantic versioning; release bar (section 6) met for every asset; compliance pack approved by Security and Legal; support model live; first client conversation booked.

---

## 4. Timeline at a glance

| Week | 1–2 | 3–4 | 5–6 | 7–8 | 9–10 | 11–13 | 14–16 |
|---|---|---|---|---|---|---|---|
| Mobilise | ■ | | | | | | |
| WS-A TCO toolkit | | ■ | ■ | ■ | ◪ | | |
| WS-B Delta→Iceberg | | ■ spike | ■ | ■ | | | |
| WS-C Snowflake SQL | | ■ | ■ | ■ | ◪ | | |
| WS-D Reconciliation | | | | | ■ | ■ | |
| WS-E Governance | | | | | ■ | ■ | |
| WS-F Orchestration | | | | | | ■ | |
| WS-G Notebooks/DLT | | | | | ■ | ■ | |
| Harden & GTM | | | | | | | ■ |
| **Gates** | G0 | | | G1 | | G2 | G3 |

■ primary effort · ◪ hardening / bug-fix

Indicative effort: ~5.2 FTE × 16 weeks ≈ **80–85 person-weeks** at 60–80% allocation (includes 0.2 FTE security lead, 0.2 FTE UK/EU onshore anchor from week 10, and the enterprise release bar; add ~5 person-weeks if an external pen-test is required). If allocation drops below 50%, extend to 20 weeks or defer WS-F and WS-G to v1.1.

---

## 5. Definition of done per asset

| Asset | Done means |
|---|---|
| Assessment & TCO | Runs against a metadata export with no code changes; TCO within ±20% of a hand-built estimate on the internal dataset; wave plan produced |
| Delta → Iceberg | 100% of internal tables converted; row counts and checksums match; time-travel behaviour documented per table type; Athena, Redshift Spectrum and EMR all read the result |
| Snowflake SQL → Redshift | ≥80% of benchmark clean; every unconverted construct has a documented manual pattern |
| Governance mapping | All internal grants/RLS/masks reproduced in Lake Formation; gap register signed off by security lead |
| Orchestration | 8+ patterns each with a working example and test |
| Reconciliation | Detects seeded discrepancies (dropped rows, mutated values, precision drift) in the test suite; sign-off report generated |
| Notebook/DLT templates | 30 internal notebooks/pipelines migrated; runtime within 1.5× of Databricks baseline |
| Reference arch & runbook | Reviewed by AWS PSA; used in one client conversation |

---

## 6. Enterprise-grade engineering standards (release bar)

Every asset must meet all of the following before it is tagged as releasable. This is what separates an accelerator from a collection of scripts and is what a client CISO or procurement team will ask for.

**Secure development lifecycle**
- Threat model per asset (STRIDE-lite) covering: source credential handling, data in transit, data at rest in staging buckets, converted-code injection risks, logging of sensitive values.
- CI gates: SAST (Semgrep/Bandit), dependency vulnerability scan (Trivy/Grype), secret scanning (gitleaks), IaC scan (Checkov/tfsec). Any High/Critical blocks the merge.
- Signed commits, protected main branch, mandatory peer review (two reviewers for WS-B and WS-E code).
- SBOM (CycloneDX) generated per release; third-party licence check automated (no GPL/AGPL in distributed components without Legal approval).

**Identity, secrets and access**
- No static credentials anywhere. Source-system access via short-lived tokens (Databricks OAuth M2M, Snowflake key-pair with rotation); AWS access via IAM roles with least-privilege policies shipped as IaC.
- Secrets only in AWS Secrets Manager / client's vault; tooling reads at runtime, never persists.
- Every asset runs under a documented, minimal IAM policy that a client security team can review and approve before execution.

**Data protection**
- Encryption in transit (TLS 1.2+) and at rest (KMS CMK, client-managed key supported) for all staging and output locations.
- Reconciliation harness never exports raw row data by default; sampled row-level diffs are opt-in, masked by default, and written only to a client-controlled bucket.
- Assessment toolkit collects metadata and usage statistics only — no table contents. This is stated explicitly in the data-handling statement.
- Configurable data residency: all components deployable in a single client-chosen region with no cross-region calls.

**Observability and audit**
- Structured logging (JSON) to CloudWatch with correlation IDs across assess → convert → migrate → reconcile.
- Every run produces an immutable execution record (who, what, when, source/target, row counts, checksums, outcome) suitable for change-approval evidence.
- CloudTrail data events enabled on staging buckets; Lake Formation audit events retained per client policy.

**Quality**
- Test pyramid: unit tests on conversion logic (≥80% coverage), golden-file tests against the benchmark set, integration tests against live sandbox services, end-to-end test on the internal dataset run nightly.
- Regression suite grows with every client engagement: any construct that required manual intervention becomes a test case.
- Performance baselines recorded and tracked (conversion throughput, reconciliation runtime per TB).

**Reliability and operations**
- Idempotent, resumable runs with checkpointing (a failed migration wave restarts from the last good table, not from zero).
- Rollback procedure per asset, rehearsed at Gate 2. Source systems are never modified — all assets are read-only against Databricks/Snowflake.
- Semantic versioning; backward-compatible config schemas; documented upgrade path.

**Documentation**
- Per asset: architecture decision records (ADRs), operator runbook, IAM policy, threat model summary, known limitations register, client-facing one-pager.
- Programme-level: reference architecture (aligned to AWS Well-Architected), cut-over playbook, hypercare guide.

---

## 7. Compliance and regulatory alignment

The accelerators will be run inside client estates in regulated industries, predominantly FSI. The plan therefore treats compliance as a build deliverable, not an afterthought.

### 7.1 Build-time compliance (ACC's own obligations)
- **No client or production data in the build.** Synthetic or fully anonymised internal data only; a signed data-handling statement from the lead architect at Gate 0 and re-attested at Gate 3.
- **ACC ISMS alignment.** ACC holds both ISO 27001 and SOC 2; build environment and repo controls are mapped to both (ISO 27001:2022 Annex A and SOC 2 Trust Services Criteria — Security, Availability, Confidentiality). Evidence collected continuously via CI and AWS Config so the accelerator programme falls inside the scope of the next surveillance audit / SOC 2 Type II period without a separate evidence exercise. Confirm with the ISMS owner whether the sandbox account needs to be added to the certification scope statement.
- **UK/EU data transfer posture.** No client data is processed during the build, so no transfer mechanism is needed at build time. At engagement time, assets deploy inside the client's own AWS account and region; ACC personnel access is governed by the engagement contract (SCCs / UK IDTA where ACC acts as processor from India). This is stated in the compliance pack.
- **Third-party and open-source governance.** Licence register maintained; vendor terms (Databricks, Snowflake, AWS Marketplace if listed) reviewed by Legal; export-control check if any cryptographic components are distributed.
- **IP.** Clear statement of ACC-owned IP vs. Apache-2.0 dependencies; contributor agreements for anyone outside the core team.

### 7.2 Client-side compliance (what the assets must support)

The client base spans India, the UK and the EU. Regimes are grouped by jurisdiction; the asset controls are common, with jurisdiction-specific configuration (residency, retention, transfer posture) exposed as parameters rather than forks.

**Cross-jurisdiction (all clients)**

| Regime | Relevance | How the assets support it |
|---|---|---|
| **SOC 2 / ISO 27001** (client's own certification) | All enterprise clients | Execution records and IaC provide change-management and access evidence; assets deployable inside client's existing control boundary |
| **PCI DSS 4.0** | Card data in scope | Column-level masking preserved in Lake Formation; segregation of PCI-scoped tables supported in wave planning; encryption with client CMKs |
| **BCBS 239 / model-risk expectations** | Risk data aggregation, reporting lineage | Reconciliation sign-off report and lineage-preserving governance mapping provide evidence of data integrity through migration |
| **AWS Well-Architected — Security & Reliability pillars; AWS FSI Lens** | All AWS deployments | Gate 1 review; findings tracked to closure |

**India**

| Regime | Relevance | How the assets support it |
|---|---|---|
| **RBI** — IT outsourcing directions (2023), cyber security framework, payments data localisation (2018 circular) | Banks, NBFCs, payment firms | Single-region (ap-south-1 / ap-south-2) deployment; full audit trail; read-only against source; no ACC-hosted processing |
| **DPDP Act 2023** and rules | Any personal data in migrated tables | Metadata-only assessment; masked reconciliation; governance mapping preserves purpose-limiting controls; consent/purpose metadata carried as LF-Tags where present |
| **SEBI / IRDAI** cyber guidelines | Capital markets, insurance | Same control set as RBI; audit-log retention configurable to regulator minimums |

**United Kingdom**

| Regime | Relevance | How the assets support it |
|---|---|---|
| **UK GDPR / Data Protection Act 2018; DUA Act 2025 amendments** | Personal data | DPIA template; masked reconciliation; residency in eu-west-2; UK IDTA / Addendum for any ACC processor access from India |
| **FCA / PRA operational resilience (SS1/21, PS21/3), PRA SS2/21 outsourcing and third-party risk** | Banks, insurers, investment firms | Migration runbook includes important-business-service impact mapping, rollback and tolerance testing evidence; ACC sub-outsourcing disclosures in the compliance pack |
| **FCA Consumer Duty** (indirect) | Retail firms | Data-integrity evidence from reconciliation supports fair-outcome reporting continuity |
| **Bank of England / PRA critical third-party regime** (2025) | Where AWS is designated | Reference architecture documents AWS dependency and exit/portability via open formats (Iceberg) |

**European Union**

| Regime | Relevance | How the assets support it |
|---|---|---|
| **GDPR** | Personal data | DPIA template; Art. 28 processor terms template; residency in EU regions; SCCs for ACC processor access from India; data-minimisation by design (metadata-only assessment) |
| **DORA (Regulation 2022/2554, applicable since Jan 2025)** | All EU financial entities | ICT third-party register entry template for the accelerator engagement; ICT risk-management evidence (threat models, testing, rollback); exit strategy supported by open table formats; incident-classification hooks in execution logging |
| **EBA Guidelines on outsourcing / ICT and security risk management** | Banks, payment institutions | Sub-outsourcing disclosure; audit and access rights preserved because processing stays in the client's account |
| **EU AI Act** (limited relevance) | If TCO toolkit uses ML-based workload classification | Documented as a minimal-risk system; deterministic rules preferred over ML for classification to avoid scope |
| **NIS2** | Where the client is an essential/important entity | Supply-chain security evidence (SBOM, signed releases, vulnerability management) |

### 7.3 Compliance pack (deliverable at Gate 3)
1. Data-handling and data-flow statement per asset (what is read, what is written, where, encrypted how).
2. Control mapping matrix: asset controls → ISO 27001:2022 Annex A, SOC 2 TSC, RBI cyber framework, DPDP obligations, UK GDPR/PRA SS2/21, GDPR/DORA/EBA outsourcing requirements.
3. Pre-filled responses to common client security questionnaires (SIG Lite / CAIQ-style) for the accelerator stack.
4. IAM policies, network requirements and egress list for client security review.
5. Threat model summaries and pen-test/security review attestation.
6. Third-party licence register and SBOM.
7. DPIA template (UK and EU variants), residency configuration guide, and cross-border access statement (SCCs / UK IDTA position).
8. DORA ICT third-party register entry template and PRA SS2/21 outsourcing notification support pack.
9. Exit and portability statement (how Iceberg/open formats and IaC support regulator exit-plan expectations).

### 7.4 Governance of the programme itself
- **Steering committee** (monthly): practice lead, delivery lead, security lead, AWS alliance lead. Approves gates, budget, scope changes.
- **Architecture review board**: signs off reference architecture at Gate 1 and any material design change thereafter.
- **RACI** maintained per workstream; Security and Legal are Consulted on all gates and Accountable for the compliance pack approval.
- **Change control**: scope changes after Gate 1 go through a lightweight change request with impact on timeline/effort stated.
- **Risk register** reviewed fortnightly; risks in section 9 are the starting set.

---

## 8. Team, delivery model and cadence

### 8.1 Delivery model (engagement time)
Hybrid by default, configurable per client's regulatory posture:

| Tier | Where | Roles | When used |
|---|---|---|---|
| **India delivery centre** | Pune / Bengaluru / Hyderabad (as ACC footprint allows) | Build team, conversion engineers, reconciliation and test, L2 support | Default for all clients; sole model for Indian clients and for UK/EU clients whose risk team accepts remote processor access under SCCs/IDTA |
| **UK/EU onshore** | London; Dublin or Frankfurt for EU | Engagement architect, governance/compliance lead, client-facing PM, privileged-access operator for cut-over | Offered as a standard SOW option; required where the client's PRA SS2/21 / DORA assessment restricts offshore privileged access, or where data cannot be viewed offshore even in masked form |
| **Follow-the-sun** | India + UK/EU combined | Cut-over and hypercare windows | Parallel-run and cut-over weekends; shortens the hypercare window and gives clients a same-time-zone escalation point |

Design consequences for the build:
- All assets run inside the client's AWS account; no ACC-hosted processing in any tier, so the choice of tier changes who operates the tooling, not where data goes.
- Privileged-access boundary is explicit: the runbook distinguishes read-only assessment/conversion tasks (offshore-eligible) from cut-over and credential-bearing tasks (onshore-eligible when required).
- Rate card and estimator carry both India and UK/EU day rates so the TCO and SOW can present the onshore option transparently.
- Pilot plan: one Indian FSI client and one UK/EU FSI client, so both tiers are exercised before v1 is declared production-ready.

### 8.2 Build team

- **Lead architect** — owns design decisions, AWS relationship, Gate reviews. Splits time across WS-A and WS-E.
- **Senior engineers (3)** — WS-B ×2 (then WS-G), WS-C ×1 (then WS-D).
- **Mid-level engineer** — WS-C support, then WS-F; owns CI, test fixtures and repo hygiene throughout.
- **Product/GTM owner (0.5)** — collateral, estimator, pilot client pipeline, partner programme paperwork.
- **Security lead (0.2, from ACC security function)** — threat-model review, CI security gate ownership, compliance pack co-author, pen-test coordination.
- **Legal / commercial (as needed)** — licence review, IP statement, vendor terms, SOW language.
- **UK/EU onshore anchor (0.2, from week 10)** — a UK- or EU-based senior architect who reviews the compliance pack against PRA/DORA expectations, fronts the UK/EU pilot, and becomes the onshore lead for the delivery model above.

### 8.3 Cadence
Weekly 30-min stand-down (blockers + burn), fortnightly demo to practice leadership, gate reviews as scheduled. Track in a single board; one epic per workstream.

---

## 9. Key risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Bench pulled onto billable work mid-build | High | Ring-fence WS-B and WS-C engineers formally; treat WS-F/WS-G as deferrable; agree a kill/pause rule at Gate 1 |
| Delta → Iceberg metadata conversion not feasible for some table types | Medium | Two-week spike up front; fall back to rewrite with documented cost; be transparent in collateral |
| AWS native tooling (Q Developer, SCT, Glue migration) closes the gap we're building for | Medium | Build on it, not against it; concentrate ACC IP on FSI governance, reconciliation and DLT semantics — least likely to be productised by AWS |
| Databricks/Snowflake licence terms restrict using trial accounts for tooling development | Low–Med | Use existing internal accounts; check terms before Phase 0 ends |
| Vendor counter-moves (Databricks/Snowflake price cuts) weaken the cost-driven demand signal | Medium | TCO toolkit models sensitivity; positioning also leans on lock-in reduction and open-format ownership, not price alone |
| Internal dataset too clean to be representative | Medium | Seed awkward cases deliberately in Phase 0 (see above) |
| Client security team rejects tooling at engagement start | Medium | Compliance pack, minimal IAM policies and read-only guarantee ready at Gate 3; design for deployment inside the client's own account with no ACC-hosted components |
| Security gates slow delivery | Medium | Baseline CI security in Phase 0 so it is never a late surprise; security lead embedded from week 1 |
| Regulatory interpretation gaps (e.g. RBI localisation for specific data classes, DORA sub-outsourcing thresholds) | Medium | Document assumptions; residency and retention configurable rather than hard-coded; validate with one Indian and one UK/EU client's compliance team during pilot |
| Cross-border delivery from India into UK/EU regulated clients challenged | Medium | Hybrid delivery model (section 8.1): processing stays in client account; ACC access is remote, logged and contractually covered (SCCs/IDTA); onshore UK/EU roles available as a standard SOW option |

---

## 10. Success metrics (first two quarters post-v1)

- Assessments delivered using the toolkit: target 3+
- Assessment-to-migration conversion: target ≥1 paid migration
- Effort reduction vs. bespoke approach: target 30% on assessment, 20% on migration build
- AWS: competency/programme evidence submitted; at least one co-sell opportunity registered

---

## 11. Immediate next steps (this fortnight)

1. Confirm named engineers and allocation percentages with delivery leadership.
2. Approve sandbox budget and open the AWS account / Databricks / Snowflake fixtures.
3. Book AWS PSA intro and the week-8 architecture review.
4. Select or synthesise the internal dataset; list the awkward cases to seed.
5. Freeze the benchmark query and notebook set.
6. Nominate the security lead and brief Legal on licence/vendor-terms review.
7. Confirm with the ISMS owner whether the sandbox account joins the ISO 27001 / SOC 2 scope; agree the audit evidence hand-off.
8. Engage Legal on UK/EU processor terms (SCCs, UK IDTA, Art. 28 template) and DORA/PRA outsourcing disclosure language for the SOW.
9. Nominate the UK/EU onshore anchor and confirm India delivery centre capacity for the pilots; add both rate tiers to the estimator.
10. Schedule Gate 0 for end of week 2.
