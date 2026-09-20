"""S4 — rewrite with CDF preservation (SPEC §5).

S3, then materialise the CDF window into a companion Iceberg changelog table
`{table}__changes` carrying the same schema plus `_change_type`,
`_commit_version` and `_commit_timestamp` (AT-05).

Chosen only when CDF is enabled **and** lineage shows a `table_changes()`
consumer; CDF-enabled tables with no consumer route to S3/S1 with the warning
`CDF_UNUSED_DROPPED`. The window is `options.cdf_window_days` (default 30); a
shorter Delta CDF retention truncates it and emits `CDF_WINDOW_TRUNCATED`.
"""

from __future__ import annotations

from table_mcp.schemas import ConversionOptions, ConversionTarget, TableProfile

CHANGELOG_SUFFIX = "__changes"
CHANGELOG_COLUMNS: tuple[str, ...] = ("_change_type", "_commit_version", "_commit_timestamp")


def convert(
    profile: TableProfile,
    *,
    options: ConversionOptions,
    target: ConversionTarget,
    staging: str,
    run_id: str,
    attempt: int,
) -> tuple[str, str]:
    """Return the table's and the changelog table's Iceberg metadata locations."""
    raise NotImplementedError("SPEC §5 S4 CDF preservation")
