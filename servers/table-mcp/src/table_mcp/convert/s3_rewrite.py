"""S3 — rewrite (compacting copy) (SPEC §5).

Submits the EMR Serverless Spark job in `spark_jobs/rewrite_job.py`: read Delta
at the latest version, write Iceberg v2 with target file size and sort order,
optionally redesigning the partition spec (opt-in, Gate 0 #2).

Chosen for deletion vectors, `id`-mode column mapping, generated or identity
columns, any non-identity partition scheme, the tiny-file pathology
(>10,000 files AND median file size <8 MB), a requested re-layout, or
`timestamp_mode = "ntz_utc"`.
"""

from __future__ import annotations

from table_mcp.schemas import ConversionOptions, ConversionTarget, TableProfile

# Tiny-file pathology thresholds (SPEC §5, AT-09). Both must hold.
TINY_FILE_COUNT_THRESHOLD = 10_000
TINY_FILE_MEDIAN_BYTES_THRESHOLD = 8 * 1024 * 1024


def convert(
    profile: TableProfile,
    *,
    options: ConversionOptions,
    target: ConversionTarget,
    staging: str,
    run_id: str,
    attempt: int,
) -> str:
    """Submit the rewrite job and return the Iceberg metadata location."""
    raise NotImplementedError("SPEC §5 S3 rewrite")
