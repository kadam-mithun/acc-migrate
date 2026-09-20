# ADR-0001: KMS enforcement for table-mcp writes
- Status: accepted
- Date: 2026-09-16
- Spec reference: servers/table-mcp/SPEC.md §10, §14 #7
## Context
The v0.1 rule "every S3 write goes through one KMS helper" cannot be enforced: Spark on EMR Serverless and PyIceberg FileIO write to S3 directly.
## Decision
Three independent layers: (1) `execute_conversion` refuses without `options.kms_key_arn`; (2) `storage.py` builds Spark (`fs.s3a.server-side-encryption*`) and PyIceberg (`s3.sse.*`) configuration so both libraries write SSE-KMS natively; (3) the Terraform module attaches a bucket policy denying `s3:PutObject` without `aws:kms` on staging and production prefixes.
## Consequences
Enforcement is verifiable by policy and by inspecting object encryption headers in validation; no wrapper is needed. Any new writer must be added to `storage.py` config builders and covered by the bucket policy.
## Alternatives considered
Monkey-patching library write paths (fragile); post-write encryption audit only (detects, does not prevent).
