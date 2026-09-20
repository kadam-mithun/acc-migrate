"""Startup self-check (SPEC §10). Failure is a hard stop; the server refuses to
start (AT-14).

Three checks:

a. **Databricks** — resolve effective privileges for the service principal
   including group inheritance, ownership and catalog/schema-level grants via
   `information_schema.*_privileges` and `system.access`. Any `MODIFY`,
   `CREATE*`, `WRITE*`, `MANAGE` or ownership on an in-scope securable is a hard
   stop, and the error names the grant.
b. **AWS** — `iam:SimulatePrincipalPolicy` for `s3:PutObject`/`DeleteObject` on
   every discovered source prefix must return a deny (implicit or explicit);
   `allowed` is a hard stop.
c. **Disjointness** — every staging/production prefix is disjoint from every
   discovered source location.
"""

from __future__ import annotations

from table_mcp.schemas import ConversionTarget

WRITE_PRIVILEGES: frozenset[str] = frozenset(
    {"MODIFY", "CREATE", "CREATE_TABLE", "CREATE_SCHEMA", "WRITE_FILES", "MANAGE", "ALL_PRIVILEGES"}
)


def check_databricks_privileges(catalogs: list[str]) -> None:
    """(a) Hard stop on any effective write grant or ownership."""
    raise NotImplementedError("SPEC §10 self-check (a)")


def check_source_write_denied(source_prefixes: list[str]) -> None:
    """(b) Hard stop unless IAM simulation denies writes on every source prefix."""
    raise NotImplementedError("SPEC §10 self-check (b)")


def check_prefix_disjointness(source_prefixes: list[str], *, target: ConversionTarget) -> None:
    """(c) Hard stop on any staging/source overlap."""
    raise NotImplementedError("SPEC §10 self-check (c)")


def run_all(catalogs: list[str], source_prefixes: list[str], *, target: ConversionTarget) -> None:
    """Run every check at startup, in order. Raises on the first failure."""
    raise NotImplementedError("SPEC §10 startup self-check")
