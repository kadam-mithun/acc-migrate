# `table-mcp-role` — not yet written, by design

**No Terraform in this module yet.** SPEC §10 is explicit: the IAM policy is
shipped as this module, and its **module design must be approved by a human at
Session 5 before any Terraform is written**. Root CLAUDE.md adds that any PR
touching IAM Terraform needs two human reviewers and the `needs-two-reviewers`
label, and that any change to IAM policies or KMS usage is a stop-and-ask.

Scaffolding a placeholder `main.tf` would put an unreviewed IAM policy in the
repo, so this directory holds the requirement instead.

## What the approved design must cover (SPEC §10)

Every statement on a named ARN; no wildcards on resources; `checkov` clean.

- `s3:GetObject`, `s3:ListBucket` on the source prefixes — **read only**
- `s3:*Object` on `iceberg/staging/*`, `iceberg/*`, `acc-migrate/evidence/*`
- `glue:*Table`, `glue:*Database` on the named databases
- `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey` on the client CMK
- `emr-serverless:StartJobRun/GetJobRun/CancelJobRun/ListJobRuns` on the named
  application, plus `iam:PassRole` for the job execution role
- `iam:SimulatePrincipalPolicy` on its own role ARN (startup self-check)
- `athena:StartQueryExecution/GetQueryExecution/GetQueryResults` on the named
  workgroup, plus `s3:*Object` on `acc-migrate/athena-results/*`
- `redshift-data:ExecuteStatement/DescribeStatement/GetStatementResult` and
  `redshift-serverless:GetCredentials` on the named workgroup
- `dynamodb:*Item`, `dynamodb:Query`, `dynamodb:UpdateItem` on the run table
- `secretsmanager:GetSecretValue` on the one Databricks secret

Nothing else.

Layer 3 of the KMS enforcement also belongs here (SPEC §10, ADR-0001): a bucket
policy denying `s3:PutObject` without `aws:kms` on the staging and production
prefixes.
