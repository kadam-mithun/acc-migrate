"""EMR Serverless job for S4 — CDF changelog materialisation (SPEC §5, §13).

Materialises the Change Data Feed window into the companion Iceberg table
`{table}__changes`, carrying the source schema plus `_change_type`,
`_commit_version` and `_commit_timestamp` (AT-05). The window is
`options.cdf_window_days` (default 30), truncated to the Delta CDF retention
with `CDF_WINDOW_TRUNCATED` when that is shorter.

Same constraints as `rewrite_job.py`: attempt-scoped prefix, SSE-KMS from
`storage.py`, never a write to source.
"""

from __future__ import annotations


def main() -> None:
    """Entry point invoked by `emr-serverless:StartJobRun`."""
    raise NotImplementedError("SPEC §5 S4 CDF job")


if __name__ == "__main__":
    main()
