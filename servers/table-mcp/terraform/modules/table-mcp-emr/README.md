# `table-mcp-emr` — not yet written, by design

**No Terraform in this module yet.** It provisions the shared EMR Serverless
application used by the S3/S4 rewrite jobs and its job execution role, so it
carries the same Session 5 human-approval gate as `table-mcp-role`
(SPEC §10, root CLAUDE.md).

## What the approved design must cover

- One EMR Serverless application per run, shared across tables, with maximum
  capacity taken from `options.emr_max_capacity` (SPEC §9).
- A job execution role that can read the source prefixes and write **only**
  under the attempt-scoped staging prefixes (SPEC §9).
- SSE-KMS enforced on every write with the client CMK (SPEC §10, ADR-0001).
- `checkov` clean; every resource a named ARN.
