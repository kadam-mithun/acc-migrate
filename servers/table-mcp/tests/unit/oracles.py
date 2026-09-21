"""Loader and profile builder for the human-authored oracles (SPEC §11).

The YAML under `tests/fixtures/expected/` is the source of truth, transcribed
from the SPEC §5 tables by a person. This module only *reads* it — it never
writes to it, and nothing here derives an expectation from `table_mcp` output
(root rule 5).

`build_profile` turns the sparse `profile:` description in the oracle into a
full `TableProfile`. Everything unstated is the plain-table shape of AT-01: no
Delta features, one identity partition, a handful of ordinary columns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from table_mcp.schemas import (
    ColumnMappingMode,
    ColumnProfile,
    DeltaProtocol,
    DeltaVersionEntry,
    PartitionColumn,
    TableFeatures,
    TableProfile,
    TableRef,
)

EXPECTED_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "expected"

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def load_oracle(name: str) -> dict[str, Any]:
    """Load `strategy.yaml` or `types.yaml`."""
    loaded = yaml.safe_load((EXPECTED_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):  # pragma: no cover - empty oracle
        return {}
    return loaded


def build_profile(spec: dict[str, Any] | None) -> TableProfile:
    """Build a `TableProfile` from an oracle's sparse `profile:` block."""
    spec = dict(spec or {})

    columns = [
        ColumnProfile(name=column["name"], delta_type=column["type"])
        for column in spec.get("columns", [])
    ] or [
        ColumnProfile(name="trade_date", delta_type="DATE"),
        ColumnProfile(name="notional", delta_type="DECIMAL(18,2)"),
    ]

    partition_columns = [
        PartitionColumn(
            name=partition["name"],
            identity=partition.get("identity", True),
            source_column=partition.get("source_column"),
            generated_expression=partition.get("generated_expression"),
        )
        for partition in spec.get("partition_columns", [])
    ] or [PartitionColumn(name="trade_date", identity=True, source_column="trade_date")]

    version_ledger = [
        DeltaVersionEntry(
            version=entry["version"],
            timestamp=_EPOCH,
            operation="WRITE",
            file_set_hash=f"h{entry['version']}",
            recoverable=entry.get("recoverable", True),
        )
        for entry in spec.get("version_ledger", [])
    ]

    features = TableFeatures(
        deletion_vectors=spec.get("deletion_vectors", False),
        column_mapping=ColumnMappingMode(spec.get("column_mapping", "none")),
        change_data_feed=spec.get("change_data_feed", False),
        cdf_retention_days=spec.get("cdf_retention_days"),
        liquid_clustering=spec.get("liquid_clustering", False),
        clustering_columns=spec.get("clustering_columns", []),
        generated_columns=spec.get("generated_columns", []),
        identity_columns=spec.get("identity_columns", []),
        row_tracking=spec.get("row_tracking", False),
        type_widening_unsupported=spec.get("type_widening_unsupported", []),
        uniform_iceberg=spec.get("uniform_iceberg", False),
        uniform_metadata_location=spec.get("uniform_metadata_location"),
    )

    return TableProfile(
        table_ref=TableRef(catalog="meridian_fin", schema_name="gl", name="trades_plain"),
        protocol=DeltaProtocol(min_reader_version=1, min_writer_version=2),
        features=features,
        columns=columns,
        partition_columns=partition_columns,
        version_ledger=version_ledger,
        version_count=len(version_ledger),
        latest_version=max((entry.version for entry in version_ledger), default=0),
        active_file_count=spec.get("active_file_count", 120),
        total_size_bytes=spec.get("total_size_bytes", 1024 * 1024 * 1024),
        median_file_size_bytes=spec.get("median_file_size_bytes", 256 * 1024 * 1024),
        dlt_managed=spec.get("dlt_managed", False),
        cdf_consumers=spec.get("cdf_consumers", []),
        downstream_consumers=spec.get("downstream_consumers", []),
        log_corrupted=spec.get("log_corrupted", False),
    )
