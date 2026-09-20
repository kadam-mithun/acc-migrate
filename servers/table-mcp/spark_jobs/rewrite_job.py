"""EMR Serverless job for S3 — rewrite (compacting copy) (SPEC §5, §13).

Reads Delta at the pinned version with delta-rs/Spark and writes Iceberg v2 with
the target file size and sort order, optionally redesigning the partition spec.

Constraints this job must honour:

* it receives `run_id` and `attempt` and writes **only** under the
  attempt-scoped staging prefix, so a late orphan can never commit into a newer
  attempt's location (SPEC §9);
* SSE-KMS settings come from `storage.spark_sse_config`; the job never writes
  without a CMK (SPEC §10);
* it never writes to Databricks or any source prefix (root rule 2);
* it is also runnable locally with `pyspark` for tests (root conventions).
"""

from __future__ import annotations


def main() -> None:
    """Entry point invoked by `emr-serverless:StartJobRun`."""
    raise NotImplementedError("SPEC §5 S3 rewrite job")


if __name__ == "__main__":
    main()
