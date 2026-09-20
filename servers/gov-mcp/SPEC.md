# `gov-mcp` — Unity Catalog → Lake Formation Governance Mapping Service
## Build Specification v0.2 (Gate 0 condition 3 — open questions resolved 16 Sep 2026)

**Owner:** Lead architect · **Co-owner:** Security lead · **Reviewers:** Senior engineer (WS-E), Legal (gap-register disclosure language)
**Repo path:** `acc-migrate/servers/gov-mcp/` · **Language:** Python 3.12, boto3, Terraform 1.9, OPA/Rego
**Status:** Ready for Gate 0; section 13 decisions taken by the practice lead, security lead to countersign. This is the moat item; ambiguity here is expected and is resolved by the gap taxonomy in section 6, not by improvisation.

---

## 1. Purpose

Extract the complete access-control model of a Unity Catalog estate — privileges, ownership, row filters, column masks, tags and ABAC policies — and translate it into an equivalent Lake Formation and Glue Data Catalog model on AWS, producing (a) Terraform that a human approves and applies, (b) a signed gap register for everything that does not translate one-to-one, and (c) control-mapping evidence for the compliance pack. Never applies permissions itself.

**Not in scope:** Snowflake RBAC (Phase B); IAM Identity Center / IdP group provisioning (documented dependency, section 4); Redshift-native RLS and masking beyond what the gap resolutions require; workspace-level ACLs (clusters, jobs, secrets) — those belong to `jobs-mcp`.

---

## 2. Design principles

1. **Propose, never apply.** Output is a Terraform plan and a register. `apply` happens through `aws-mcp` with an approval id from the ledger, or by the client's own pipeline. This server holds no `lakeformation:Grant*` permission.
2. **Semantic honesty.** Every policy is classified as *equivalent*, *equivalent with different mechanism*, *weaker*, *stronger*, or *not representable*. Nothing is silently approximated.
3. **Deny-by-default on ambiguity.** Where a translation could be more permissive than source, the tool emits the more restrictive option and a gap entry, never the permissive one.
4. **Deterministic.** Same source snapshot, same output. Policy translation is a pure function over an intermediate model; no LLM in the path. Agents explain the register; they do not write it.
5. **Evidence-grade.** Source snapshot hash, translation version, decision per policy, and reviewer sign-off are all in the ledger.

---

## 3. MCP interface

| Tool | Purpose | Autonomy |
|---|---|---|
| `snapshot_source(catalogs[])` | Read the full UC governance state into a versioned `SourceSnapshot` (section 4); returns snapshot id and content hash | Read-only |
| `build_policy_model(snapshot_id)` | Normalise into the intermediate `PolicyModel` (section 5); resolves group membership and ownership inheritance | Pure function |
| `translate(policy_model_id, target_profile)` | Produce `TargetModel` (LF permissions, LF-Tags, data filters, Glue resource policies, Redshift artefacts where required) plus `GapRegister` | Pure function |
| `render_terraform(target_model_id)` | Emit Terraform modules and a `terraform plan`-ready workspace into the client repo path; run `terraform validate` and `checkov` | Writes files only |
| `test_policies(target_model_id)` | Run OPA/Rego conformance tests (section 9) and, when a staging Lake Formation environment is present, effective-permission probes | Read-only on target |
| `diff_governance(snapshot_id_a, snapshot_id_b)` | Drift between two source snapshots, or source vs. deployed target (via `lakeformation:List*`) | Read-only |
| `export_evidence(target_model_id)` | Gap register (HTML/PDF/CSV), control-mapping matrix, per-principal effective-access comparison | Read-only |
| `request_apply(target_model_id)` | Writes an approval request to the ledger with the plan, register and tests attached; **does not apply** | L1 |

All tools accept `run_id`; every call is an OTel span tagged `run_id`, `snapshot_id`, `catalog`.

---

## 4. Source extraction

**Access:** Databricks service principal, OAuth M2M; `USE CATALOG` on in-scope catalogs, `SELECT` on `system.information_schema.*`, `system.access.*`. Read-only asserted at startup (same self-check as `table-mcp`).

**Extracted objects (all via `system.information_schema` and the UC REST API, read-only):**
- Securables and hierarchy: metastore → catalogs → schemas → tables/views/volumes/functions, with owners.
- Privileges: `catalog_privileges`, `schema_privileges`, `table_privileges`, `volume_privileges`, `routine_privileges`, including `inherited_from`.
- Principals: users, groups (with nested membership resolved via SCIM API), service principals.
- Row filters and column masks: `information_schema.row_filters`, `column_masks`, plus the SQL bodies of the masking/filtering functions from `routines`.
- Tags: `information_schema.catalog_tags`, `schema_tags`, `table_tags`, `column_tags`.
- ABAC policies (governed tags / `CREATE POLICY` objects where the workspace has them enabled) via REST API.
- Dynamic views: views whose definitions reference `current_user()`, `is_account_group_member()`, `is_member()` or `current_catalog()`.
- Lineage (`system.access.table_lineage`) to identify downstream consumers of masked/filtered tables.

**Identity dependency:** UC groups must resolve to IAM Identity Center groups, IAM roles, or Redshift roles on the target. The client provides a `principal_map.yaml` (UC group → target principal ARN/role). Unmapped principals are a **blocking gap** (G-ID-01). This is a human input by design; the tool never guesses identities.

---

## 5. Intermediate `PolicyModel`

A source- and target-neutral model so Snowflake (Phase B) and future sources translate through the same path.

```
Principal {id, kind: user|group|service, members[], external_ref}
Securable {path, kind: catalog|schema|table|view|column|volume|function, owner, tags{}}
Grant {principal, securable, privilege ∈ canonical set, inherited: bool, source_ref}
RowPolicy {securable, function_ref, predicate_ast, params[], depends_on_session: bool}
ColumnPolicy {securable, column, function_ref, expr_ast, output_type_change: bool, depends_on_session: bool}
TagPolicy {tag_key, tag_values[], effect, principals[], source: abac|convention}
DynamicView {securable, sql_ast, session_functions_used[]}
```

Canonical privileges: `SELECT, MODIFY, CREATE_TABLE, USE_CATALOG, USE_SCHEMA, EXECUTE, READ_VOLUME, WRITE_VOLUME, BROWSE, APPLY_TAG, MANAGE, ALL_PRIVILEGES`. Predicates and masking expressions are parsed to an AST with SQLGlot (Databricks dialect) so translation reasons about structure, not strings.

---

## 6. Gap taxonomy and default resolutions

This section is the product. Each gap type has an id, a detection rule, a default resolution, an alternative, and a disclosure line for the register. Defaults are agreed with the security lead at Gate 0 and are configurable per client in `target_profile`.

### 6.1 Identity and principals
| ID | Gap | Default resolution | Alternative | Register classification |
|---|---|---|---|---|
| G-ID-01 | UC principal has no mapping in `principal_map.yaml` | **Block**: no Terraform emitted for grants to that principal | — | Blocking |
| G-ID-02 | Nested UC groups (LF principals are flat) | Flatten to effective membership at snapshot time; emit membership list as evidence; flag drift risk | Map to IdC nested groups if Identity Center supports the nesting | Equivalent with different mechanism |
| G-ID-03 | Service principal used interactively and by jobs | Emit two target principals (IAM role for jobs, IdC user/role for interactive) | Single role | Equivalent with different mechanism |

### 6.2 Privileges
| ID | Gap | Default resolution | Alternative | Classification |
|---|---|---|---|---|
| G-PR-01 | `USE_CATALOG`/`USE_SCHEMA` have no LF equivalent | Emit `DESCRIBE` on database; document that LF discovery semantics differ | — | Equivalent with different mechanism |
| G-PR-02 | `MODIFY` covers INSERT/UPDATE/DELETE together | Emit LF `INSERT, DELETE, ALTER` on table (no separate UPDATE in LF; Iceberg updates are file rewrites) | Restrict to `INSERT, DELETE` | Equivalent |
| G-PR-03 | `BROWSE` (metadata-only visibility) | Emit `DESCRIBE`; note that LF `DESCRIBE` may expose column names not visible under UC BROWSE for masked columns | Omit | Weaker (disclosed) |
| G-PR-04 | Ownership as implicit full privilege | Emit explicit LF grants to the owner principal with `grantable`; record that LF has no ownership concept on tables | — | Equivalent with different mechanism |
| G-PR-05 | Grants on volumes/functions | Volumes → S3 prefix permissions via IAM policy fragment; functions → not translated (belong to `jobs-mcp`) | — | Out of scope, documented |
| G-PR-06 | `ALL_PRIVILEGES` | Expand to the explicit LF set at translation time; never emit `ALL` | — | Equivalent |

### 6.3 Row-level security
| ID | Gap | Default resolution | Alternative | Classification |
|---|---|---|---|---|
| G-RL-01 | Row filter is a static predicate over table columns (`region IN ('UK','IE')`) | LF **data filter** with row filter expression, one per (table, principal-set) | — | Equivalent |
| G-RL-02 | Row filter depends on session context (`is_account_group_member('desk_fx')`, `current_user()`) | Enumerate group memberships at translation time and emit **one LF data filter per group**, attached to the mapped principal; record that membership changes require re-translation (`diff_governance` detects) | Redshift RLS policy using `current_user`/`SESSION_USER` for Redshift consumers; Athena consumers get enumerated filters | Equivalent with different mechanism |
| G-RL-03 | Row filter joins to a lookup/entitlement table | **Not representable** in LF data filters (single-table expressions only). Default: materialise entitlement as an Iceberg view per consumer engine (Redshift late-binding view with RLS; Athena view) and grant on the view, deny on the base table | Denormalise entitlement column into the table via `jobs-mcp` | Not representable → mechanism change (disclosed) |
| G-RL-04 | Row filter function has side effects or non-deterministic calls | Block; manual | — | Blocking |

### 6.4 Column masking
| ID | Gap | Default resolution | Alternative | Classification |
|---|---|---|---|---|
| G-CM-01 | Mask hides the column entirely for non-privileged principals | LF **column-level exclusion** (`excluded_column_names`) | — | Equivalent |
| G-CM-02 | Mask transforms the value (`'***' || right(card,4)`, hash, null-out) | **Not representable in LF** (LF can hide, not transform). Default: Redshift **dynamic data masking policy** for Redshift consumers; for Athena/EMR consumers, a masked **Iceberg view** per sensitivity tier with LF grants on the view and column exclusion on the base table | Pre-materialise masked columns as additional columns (`card_masked`) via `jobs-mcp` | Not representable → mechanism change (disclosed) |
| G-CM-03 | Mask depends on session context (`CASE WHEN is_member('pii_readers') THEN col ELSE mask`) | Split into tiers: one view/mask policy per principal set; LF grants route principals to the right tier | Redshift DDM with `current_user` conditions | Equivalent with different mechanism |
| G-CM-04 | Mask changes output type (e.g. STRING → NULL vs. STRING → INT) | Preserve type of the masked expression; register notes downstream type impact | — | Equivalent (disclosed) |
| G-CM-05 | Masking function references another table | Same as G-RL-03 | — | Not representable → mechanism change |

### 6.5 Tags and ABAC
| ID | Gap | Default resolution | Alternative | Classification |
|---|---|---|---|---|
| G-TG-01 | UC tags used as metadata only | Glue table/column parameters `uc_tag:<key>` and LF-Tags (key/value) | — | Equivalent |
| G-TG-02 | UC ABAC policy (`CREATE POLICY ... ON tag`) | LF **tag-based access control**: LF-Tag expression permission to the mapped principal; verify tag value sets match | — | Equivalent |
| G-TG-03 | Tag value cardinality exceeds LF-Tag limits (values per tag / tags per resource) | Partition tag into `<key>_1..n` and document | Collapse rarely used values | Equivalent with different mechanism |
| G-TG-04 | Tag inheritance semantics differ (UC catalog tag does not imply column tag) | Emit explicit tags at each level; do not rely on LF inheritance | — | Equivalent (disclosed) |
| G-TG-05 | Target database still grants `IAMAllowedPrincipals` (bypasses LF) | **Block**: no grants emitted until client confirms revocation in ledger | — | Blocking |

### 6.6 Dynamic views
| ID | Gap | Default resolution | Classification |
|---|---|---|---|
| G-DV-01 | View uses `current_user()` / `is_member()` for filtering or masking | Convert to per-principal-set views + LF grants (same pattern as G-RL-02 / G-CM-03), or Redshift view with RLS/DDM | Equivalent with different mechanism |
| G-DV-02 | View uses `current_catalog()` / `current_schema()` for routing | Resolve statically at translation | Equivalent |
| G-DV-03 | View definition cannot be parsed | Manual | Blocking |

### 6.7 Regulatory annotations
Every gap entry additionally carries: data classification of the affected columns (from UC tags or the client's `classification_map.yaml`), applicable regime flags (PCI, personal data, restricted), and whether the resolution is *stronger*, *equivalent* or *weaker* than source. Any *weaker* resolution on a PCI or personal-data column is escalated to **blocking** by default (`target_profile.strict_sensitive = true`).

---

## 7. Translation rules (normative)

1. Snapshot → PolicyModel is lossless; the snapshot is retained as evidence.
2. Translation runs in order: identities → privileges → tags → row policies → column policies → dynamic views → cross-checks.
3. Cross-checks (must all pass or produce gaps): no principal gains access on target it lacked on source (permissiveness check); every source-visible column remains visible to at least the same principals; every masked/filtered table has a corresponding mechanism for each consumer engine in `target_profile.engines`.
4. For every table with a *mechanism change* gap, the base table receives **no direct `SELECT`** for affected principals; access is via the view or Redshift object. The register states this.
5. Output is idempotent Terraform: `aws_lakeformation_permissions`, `aws_lakeformation_lf_tag`, `aws_lakeformation_resource_lf_tags`, `aws_lakeformation_data_cells_filter`, `aws_glue_catalog_table` (views), `aws_redshift_*` via SQL artefacts in `redshift/` applied by `aws-mcp`. Resource names are deterministic hashes of (securable, principal, mechanism).
6. Never emit `IAMAllowedPrincipals` grants. Presence of `IAMAllowedPrincipals` on a target database is blocking gap G-TG-05 until the client confirms revocation in the ledger (section 13, decision 4).
7. Before emitting grants for a database, check `IAMAllowedPrincipals` via `lakeformation:ListPermissions`; refuse without recorded confirmation.

---

## 8. Outputs

- `terraform/` workspace per catalog, `terraform validate` and `checkov` clean, with a generated `README` per module.
- `redshift/` SQL: RLS policies, DDM policies, views, with `--dry-run` support.
- `gap_register.{json,html,pdf,csv}` — one row per gap: id, securable, principals, source definition, target mechanism, classification, regime flags, decision (default/alternative/manual), reviewer, sign-off timestamp.
- `control_mapping.json` — per control: ISO 27001 A.5.15/A.5.18/A.8.3, SOC 2 CC6.1–6.3, PRA SS2/21 §8, DORA Art. 9, RBI cyber framework access-control clauses, DPDP purpose-limitation — with the evidence pointer.
- `effective_access_diff.csv` — per principal, per securable: source vs. target effective access.
- Ledger record with snapshot hash, translation version, outputs hash.

---

## 9. Testing and OPA conformance

- **Unit:** every gap detection rule `test_gap_<id>_detect`; every resolution `test_gap_<id>_resolve`; permissiveness cross-check with adversarial fixtures.
- **OPA/Rego suite (`policies/`):** rules that fail the build if any emitted permission is broader than source, if `ALL` appears, if `IAMAllowedPrincipals` is granted, if a PCI/personal column has a *weaker* resolution without an override, or if a principal in Terraform is absent from `principal_map.yaml`. These same Rego policies are reused by the Compliance & Policy Agent at runtime.
- **Effective-permission probes (integration, staging LF):** for a sample of principals, assume the mapped role and run `SELECT` via Athena against filtered/masked tables; compare row counts and masked values with a UC baseline captured on the fixture workspace.
- **Golden fixtures:** the synthetic FSI estate carries at least one instance of every gap id in section 6; expected outputs recorded once from the fixture workspace, never from the code under test.

---

## 10. Security and evidence

- IAM for this server: `glue:Get*`, `lakeformation:List*`, `lakeformation:GetEffectivePermissionsForPath`, `lakeformation:Describe*`, S3 write to the client repo/evidence prefix only, DynamoDB ledger, Secrets Manager for the one Databricks secret. **No `lakeformation:Grant*`/`Revoke*`, no `iam:*`.** Checkov clean.
- Source SQL bodies of masking/filter functions are treated as **untrusted input**: parsed with SQLGlot, never executed, never interpolated into shell, Terraform or prompts unescaped.
- Logs carry securable paths, principal ids and gap ids; never data values, never full masking expressions containing literals classified as sensitive (redacted to AST shape).
- Every register is signed off in the ledger by a named reviewer; the Terraform plan hash is bound to that sign-off; `aws-mcp` refuses to apply a plan whose hash differs.

---

## 11. Acceptance tests (definition of done)

| ID | Fixture | Expected | Pass criteria |
|---|---|---|---|
| AT-G01 | 3 catalogs, 40 schemas, 600 tables, 25 groups nested 3 deep, full principal map | Complete translation | Terraform valid, checkov clean, effective-access diff shows zero additional access on target |
| AT-G02 | Group with no principal mapping | G-ID-01 | Blocking gap; no Terraform emitted for that principal; register lists affected securables |
| AT-G03 | Static row filter `region IN (...)` on `trades` | G-RL-01 | One LF data filter per principal set; probe: mapped role sees identical row count to UC baseline |
| AT-G04 | Row filter using `is_account_group_member('desk_fx')` with 4 desk groups | G-RL-02 | 4 data filters emitted; register notes membership drift; `diff_governance` detects a membership change fixture |
| AT-G05 | Row filter joining entitlement table | G-RL-03 | Views emitted per engine; base table has no direct SELECT for affected principals; probe matches baseline |
| AT-G06 | Column mask `'***' || right(card_number, 4)` on PCI-tagged column, consumers Redshift + Athena | G-CM-02, regime PCI | Redshift DDM policy + masked Iceberg view; base column excluded via LF; probe shows masked value for non-privileged role; register flags PCI |
| AT-G07 | Session-dependent mask with two tiers | G-CM-03 | Two tiers emitted; principals routed correctly; probe per tier |
| AT-G08 | UC ABAC policy on tag `sensitivity=high` | G-TG-02 | LF-Tag expression permission; tag values match; probe |
| AT-G09 | Tag with 60 values | G-TG-03 | Partitioned LF-Tags; register entry |
| AT-G10 | Dynamic view with `current_user()` | G-DV-01 | Per-principal-set views; probe |
| AT-G11 | Adversarial: translation that would grant `SELECT` on a column hidden at source | Cross-check | Build fails with permissiveness violation; OPA test red |
| AT-G12 | `ALL_PRIVILEGES` on schema | G-PR-06 | Expanded explicit set; no `ALL` string in Terraform |
| AT-G13 | Weaker resolution on personal-data column with `strict_sensitive=true` | Escalation | Blocking; with `strict_sensitive=false` → disclosed gap |
| AT-G14 | `request_apply` before reviewer sign-off | — | Ledger refuses; with sign-off → approval request created; `aws-mcp` refuses a plan with a changed hash |
| AT-G15 | Startup with `lakeformation:GrantPermissions` in the role | — | Server refuses to start |
| AT-G17 | Target database with `IAMAllowedPrincipals` present | G-TG-05 | Translation refuses for that database; after ledger confirmation, proceeds; tool never issues a revoke |
| AT-G16 | Full synthetic estate | All | Register includes ≥1 of every gap id; control-mapping complete; evidence exported; runtime and cost recorded |

Coverage ≥ 90% on `translate/`, `gaps/`, `policies/`; ≥ 80% overall; OPA suite green in CI.

---

## 12. Repo layout

```
servers/gov-mcp/
  SPEC.md  CLAUDE.md  OPEN_QUESTIONS.md  pyproject.toml
  src/gov_mcp/
    server.py schemas.py
    extract/ {uc_information_schema.py, uc_rest.py, scim.py, lineage.py}
    model/ {policy_model.py, ast_parse.py}
    translate/ {identities.py, privileges.py, tags.py, row_policies.py, column_policies.py, dynamic_views.py, crosschecks.py}
    gaps/ {taxonomy.py, register.py, classification.py}
    render/ {terraform.py, redshift_sql.py, evidence.py}
    probe/ {lf_effective.py, athena_probe.py}
    ledger.py telemetry.py errors.py
  policies/ (Rego)  terraform_templates/  tests/{unit,integration,acceptance,fixtures/expected}
  terraform/modules/gov-mcp-role
```

**Server CLAUDE.md (extract):** never add `lakeformation:Grant*` to any policy or code path; gap ids are stable identifiers — never renumber; every gap id has detect + resolve tests; masking/filter SQL bodies are parsed, never executed; default to the more restrictive translation on any ambiguity and open an `OPEN_QUESTIONS.md` entry.

---

## 13. Gate 0 decisions (taken 16 Sep 2026; security lead to countersign)

| # | Question | Decision | Consequence in spec |
|---|---|---|---|
| 1 | G-CM-02 default when Redshift is not a consumer | **Masked Iceberg view per sensitivity tier**; base column excluded via LF | `translate/column_policies.py` emits one view per tier; materialisation is an opt-in alternative in `target_profile` |
| 2 | G-RL-02 with high group churn | **Enumerated LF data filters for all tables**; drift detected by `diff_governance`, which raises a re-translation request to the ledger | Redshift RLS remains an optional alternative; scheduled `diff_governance` runs are part of hypercare runbook |
| 3 | `strict_sensitive` default | **`true`** — any weaker resolution on PCI or personal-data columns blocks | Override requires named reviewer decision recorded in ledger (AT-G13) |
| 4 | `IAMAllowedPrincipals` on target databases | **Detect and block** — no grants emitted for a database until the client confirms revocation; confirmation recorded in ledger | New gap id **G-TG-05 (blocking)**; new acceptance test **AT-G17**: database with `IAMAllowedPrincipals` present → translation refuses; with confirmation → proceeds. The tool never revokes on the client's behalf |
| 5 | Identity mapping default | **IAM Identity Center groups**; IAM roles and Redshift roles as per-group overrides in `principal_map.yaml` | `translate/identities.py` default resolver; schema for `principal_map.yaml` includes `kind: idc_group \| iam_role \| redshift_role` |
| 6 | Source snapshot retention | **90 days post-engagement in the client's account, then deleted** (proposed default, not explicitly selected — confirm) | S3 lifecycle rule in `terraform/modules/gov-mcp-role`; retention configurable per client in `target_profile.snapshot_retention_days`; documented in the compliance pack data-handling statement |

Rule 7 in section 7 is amended accordingly: before any grant is emitted for a target database, `translate` checks for `IAMAllowedPrincipals` via `lakeformation:ListPermissions`; presence without a ledger-recorded client confirmation is a blocking gap.
