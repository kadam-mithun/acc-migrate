"""S6 — UniForm read-only Glue bridge (SPEC §5, Gate 0 #13, AT-22).

The table is not converted. With `options.register_bridge=true` the existing
Iceberg metadata location is registered in Glue as a read-only bridge and the
table moves to `FEDERATED`; otherwise the decision is recorded, the state is
`SKIPPED_S6` and there are **no side effects**. The eventual strategy (S1/S3) is
recorded for cut-over.
"""

from __future__ import annotations

from table_mcp.schemas import ConversionOptions, ConversionTarget, TableProfile


def register_bridge(
    profile: TableProfile, *, options: ConversionOptions, target: ConversionTarget
) -> str | None:
    """Register the Glue bridge and return its metadata location, or None when
    `register_bridge` is not set (state `SKIPPED_S6`, zero side effects)."""
    raise NotImplementedError("SPEC §5 S6 UniForm bridge")
