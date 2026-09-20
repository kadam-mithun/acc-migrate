"""S2 — metadata replay (SPEC §5, §6).

Replays Delta log versions oldest→newest within the requested window as Iceberg
snapshots using `add_files`/`delete_files` per version, tagging each snapshot
with the Delta version and commit timestamp. Zero data copy.

Vacuumed versions cannot be replayed: the window is truncated to the oldest
fully-present version, `HISTORY_TRUNCATED` is emitted, and the effective
retention boundary is recorded (AT-02).
"""

from __future__ import annotations

from table_mcp.schemas import (
    ConversionOptions,
    ConversionTarget,
    SnapshotMapping,
    TableProfile,
)


def replay_window(profile: TableProfile, *, options: ConversionOptions) -> list[int]:
    """Resolve the Delta versions to replay, truncated at the oldest recoverable one."""
    raise NotImplementedError("SPEC §6 history window")


def convert(
    profile: TableProfile, *, options: ConversionOptions, target: ConversionTarget, staging: str
) -> tuple[str, list[SnapshotMapping]]:
    """Replay the window; return the metadata location and the version→snapshot map."""
    raise NotImplementedError("SPEC §5 S2 metadata replay")
