# `fsi-fixtures` — Synthetic FSI Estate Generator
## Build Specification v0.1 (Phase 0; gates every acceptance test)

**Owner:** Mid-level engineer (harness/CI owner) · **Reviewers:** Lead architect, Security lead (synthetic-data attestation)
**Repo path:** `acc-migrate/tools/fsi-fixtures/` · **Language:** Python 3.12, PySpark 3.5, Faker, Databricks SDK, Terraform
**Status:** Draft for Gate 0. Nothing in `table-mcp` or `gov-mcp` can pass acceptance until this exists.

---

## 1. Purpose

Generate a realistic, fully synthetic Databricks/Unity Catalog estate for a fictional bank ("Meridian Bank") that exercises every strategy in `table-mcp` SPEC §5 and every gap id in `gov-mcp` SPEC §6, at a scale that makes performance numbers meaningful (≥ 1 TB total), and record golden expected outputs from it once. The same estate later seeds demos, the TCO model validation and the evaluation harness.

**Hard constraint:** zero real data. No production extracts, no "anonymised" client data, no public datasets containing real persons. Every value is generated. The security lead signs a synthetic-data attestation at Gate 0 (build plan §7.1) on the basis of this spec and the generator's provenance log.

---

## 2. Estate shape

Three catalogs mirroring a bank's domains. Counts are targets; the generator takes a `scale` parameter (`small` for CI ≈ 5 GB, `full` ≈ 1.2 TB).

| Catalog | Schemas | Tables (full) | Purpose |
|---|---|---|---|
| `meridian_ref` | `reference`, `calendar`, `product` | 40 | Reference data; small, wide, many consumers; **wave 1** |
| `meridian_fin` | `gl`, `finance_marts`, `treasury` | 180 | Finance marts; aggregates, history, CDF; **wave 2** |
| `meridian_risk` | `positions`, `market_data`, `counterparty`, `desk` | 260 | Risk and positions; large partitioned facts, RLS by desk, PCI-adjacent; **wave 3** |
| `meridian_cust` | `customer`, `kyc`, `cards`, `payments` | 120 | Customer 360; personal data, PCI, masking-heavy; **wave 4** |

Total ≈ 600 tables, ~25 groups nested three deep, ~300 users, 12 service principals, 20 DLT pipelines, 35 Workflows jobs, 80 notebooks. Sizes: 5 tables > 100 GB, 40 tables 1–100 GB, remainder < 1 GB, 30 "tiny-file" tables.

---

## 3. Named fixtures (must exist exactly as specified)

Each acceptance test references a fixture by name. The generator creates them deterministically from `seed=20260916`.

### 3.1 `table-mcp` fixtures (SPEC §11)
| Fixture | Location | Characteristics |
|---|---|---|
| `trades_plain` | `meridian_risk.positions.trades_plain` | 200M rows, identity partition `trade_date`, Parquet unmodified, no features, ~180 GB |
| `positions_history` | `meridian_risk.positions.positions_history` | 50 Delta versions across 90 simulated days (daily MERGE), retention 120 days, no VACUUM |
| `customers_dv` | `meridian_cust.customer.customers_dv` | Deletion vectors enabled, 5% soft-deleted rows, 20M rows |
| `positions_history_dv` | `meridian_risk.positions.positions_history_dv` | Copy of `positions_history` (same 50-version history) with deletion vectors enabled; exercises `HISTORY_NOT_PRESERVED` (table-mcp AT-20) |
| `ref_columns_idmap` | `meridian_ref.product.ref_columns_idmap` | Column mapping `id` mode; history includes 2 renames, 1 drop, 1 add |
| `orders_cdf` | `meridian_fin.gl.journal_cdf` | CDF enabled; a notebook consumer registered in lineage reading `table_changes()` |
| `dlt_gold_risk` | `meridian_risk.desk.dlt_gold_var` | DLT-managed gold table produced by pipeline `risk_var_pipeline` with 3 expectations |
| `mkt_data_uniform` | `meridian_risk.market_data.prices_uniform` | UniForm (Iceberg) enabled |
| `events_variant` | `meridian_cust.payments.events_variant` | One `VARIANT` column |
| `tiny_files` | `meridian_fin.treasury.rates_tiny` | 40,000 files < 2 MB |
| `gen_partition` | `meridian_fin.finance_marts.pnl_by_year` | Partitioned by generated column `year(ts)` |
| Bulk estate | all remaining tables | Mixed: 60% plain, 15% with deletion vectors, 10% liquid clustered, 10% with CDF, 5% column-mapping `name` mode |

### 3.2 `gov-mcp` fixtures (SPEC §6, §11)
| Fixture | Realises gap ids | Definition |
|---|---|---|
| Group hierarchy | G-ID-02 | `all_staff` → `risk_all` → `desk_fx`, `desk_rates`, `desk_credit`, `desk_equity`; `finance_all` → `gl_users`, `treasury_users`; `cust_ops` → `kyc_analysts`, `pii_readers`, `card_ops` |
| `svc_unmapped` | G-ID-01 | Service principal deliberately absent from `principal_map.yaml` |
| `svc_dual` | G-ID-03 | Service principal used by a job and granted interactive SQL |
| `region_filter` | G-RL-01 | Row filter `region IN ('UK','IE')` on `trades_plain` for `risk_all` |
| `desk_scope` | G-RL-02 | Row filter using `is_account_group_member('desk_<x>')` mapping `desk` column, on `positions_history` |
| `entitlement_join` | G-RL-03 | Row filter joining `meridian_risk.desk.entitlements(user, book)` on `book_positions` |
| `card_mask_last4` | G-CM-02 (PCI) | Column mask `'***' || right(card_number,4)` on `meridian_cust.cards.card_master.card_number`, tag `pci=true` |
| `pii_tiered_mask` | G-CM-03 | Mask `CASE WHEN is_account_group_member('pii_readers') THEN email ELSE sha2(email,256) END` on `customer.customer_master.email`, tag `personal_data=true` |
| `salary_hide` | G-CM-01 | Mask returning `NULL` for non-`hr_all` on `finance_marts.staff_cost.salary` |
| `dob_type_change` | G-CM-04 | Mask returning `DATE_TRUNC('year', dob)` (DATE → DATE, semantic change) |
| `abac_sensitivity` | G-TG-02 | UC ABAC policy: `sensitivity=high` → only `risk_seniors` |
| `wide_tag` | G-TG-03 | Tag `cost_centre` with 60 values across `meridian_fin` |
| `dyn_view_user` | G-DV-01 | View `positions_my_desk` filtering by `current_user()` |
| `dyn_view_catalog` | G-DV-02 | View routing on `current_catalog()` |
| `all_privs_schema` | G-PR-06 | `ALL PRIVILEGES` on `meridian_ref.reference` to `all_staff` |
| Target DB with legacy grant | G-TG-05 | Glue database `meridian_ref__staging` created **with** `IAMAllowedPrincipals` in the AWS sandbox |
| Membership drift | AT-G04 | Second snapshot after adding a user to `desk_fx` |

### 3.3 Cross-server fixtures
- `principal_map.yaml`: all groups mapped to IdC groups except `svc_unmapped`; two groups mapped to IAM roles, one to a Redshift role (exercises overrides).
- `classification_map.yaml`: PCI and personal-data columns tagged consistently with UC tags.
- `entitlements` and `desk_reference` tables for RLS joins.
- Lineage: 12 notebooks and 4 DLT pipelines reading masked/filtered tables so `gov-mcp` and `jobs-mcp` see downstream consumers.

---

## 4. Data realism rules

- Columns follow real FSI shapes: ISINs, LEIs (synthetic but checksum-valid), currency codes, ISO dates, decimal(18,4) amounts, SWIFT-like BICs, UK/IE/IN postcode formats, card PANs that pass Luhn but use the test IIN ranges (never a real issuer range).
- Referential integrity across tables (trades → counterparties → LEIs; cards → customers) so reconciliation and RLS joins behave realistically.
- Skew: 3 desks hold 60% of positions; 2 counterparties hold 20% of trades. Realistic skew stresses partition design and reconciliation sampling.
- Time: 5 years of history for facts, daily grain; late-arriving corrections in 2% of days to create real MERGE history.
- Nulls, duplicates and dirty values at realistic rates (1–3%) with a `dq_flags` column so reconciliation tolerances can be tested deliberately.
- Every generated value comes from Faker or a deterministic function of `seed`; no lookup tables of real names, companies or addresses beyond ISO code lists.

---

## 5. Generation and deployment

1. `fsi-fixtures plan --scale full` → prints estate manifest (tables, sizes, features, policies) as JSON; committed as `manifest.json`.
2. `fsi-fixtures generate --scale full --target s3://acc-sandbox-fixtures/raw/` → PySpark on EMR Serverless writes raw Parquet; ~2 hours at 64 vCPU; provenance log per table (seed, generator version, row count, checksum).
3. `fsi-fixtures deploy-databricks --workspace <url>` → Databricks SDK: creates catalogs/schemas, loads tables as Delta with the specified features (DV, column mapping, CDF, UniForm, liquid clustering, generated partitions), replays version history for `positions_history`, creates groups/users/SPs via SCIM, applies grants, row filters, column masks, tags, ABAC policies, dynamic views, DLT pipelines and Workflows jobs.
4. `fsi-fixtures deploy-aws` → Terraform: staging Glue databases (one with `IAMAllowedPrincipals`), IdC groups mirroring `principal_map.yaml`, Redshift Serverless namespace with test roles.
5. `fsi-fixtures snapshot-golden` → records expected outputs **once**: row counts, per-column aggregates, UC baseline effective access per principal (queries as each principal via SQL warehouse), masked/filtered result samples (aggregates and hashes only, no values), Delta version ledgers. Written to `tests/fixtures/expected/` in both servers with the generator version pinned. Re-recording requires a PR with reviewer approval and a note in `OPEN_QUESTIONS.md` of the consuming server.
6. `fsi-fixtures verify` → confirms the live estate matches `manifest.json` (drift check before any acceptance run).

CI uses `--scale small` on a shared Databricks fixture workspace refreshed nightly; `full` runs on demand for Gate 1/Gate 2 and AT-16/AT-G16.

---

## 6. Cost and environment

- Databricks fixture workspace: use ACC's existing account or a trial; estimated 40–60 DBU/day during generation, near zero at rest (SQL warehouse serverless, auto-stop). Confirm trial terms permit tooling development (Legal, Gate 0).
- AWS: ~1.2 TB S3 (~USD 30/month), EMR Serverless generation ~USD 150 per full run, Redshift Serverless minimum RPUs paused when idle.
- Two full estates may coexist (`v1`, `v1-drift`) for membership-drift tests.

---

## 7. Provenance and attestation

- `PROVENANCE.md` generated per run: generator commit, seed, Faker version, ISO code list sources, per-table checksums, confirmation that no external data files were read (the generator has no network access except Databricks and AWS APIs; enforced by egress policy in the sandbox).
- Security lead signs the synthetic-data attestation against `PROVENANCE.md` at Gate 0 and re-attests at Gate 3.
- The estate name "Meridian Bank", all people, LEIs, BICs and PANs are fictional; a `DISCLAIMER.md` ships with every demo export.

---

## 8. Acceptance tests for the generator itself

| ID | Check |
|---|---|
| FX-01 | `plan` output is byte-identical across two runs with the same seed |
| FX-02 | Every named fixture in §3 exists with the stated characteristic (asserted via Delta protocol/features, UC information_schema, lineage) |
| FX-03 | All PANs pass Luhn and fall in test IIN ranges; all LEIs pass checksum; no value matches any entry in a small denylist of well-known real institutions/people |
| FX-04 | Referential integrity holds at ≥ 99.9% (with the 0.1% deliberate breaks flagged in `dq_flags`) |
| FX-05 | `full` scale ≥ 1 TB; `small` ≤ 6 GB; generation completes within budget |
| FX-06 | `snapshot-golden` outputs contain no raw sensitive-class values (regex and classifier scan) |
| FX-07 | `verify` detects an injected drift (dropped table, changed grant) |

---

## 9. Open questions for Gate 0

1. Databricks fixture workspace: ACC-owned account vs. trial — Legal to confirm terms for tooling development.
2. Whether to include a small Snowflake fixture now (Phase B readiness) or defer entirely.
3. Whether the `full` estate should also be published to a Redshift cluster as a **target-side baseline** for `recon-mcp` false-positive testing.
4. Retention of the fixture estate between Gates (cost vs. regeneration time ~3 hours).
