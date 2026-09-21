"""The mechanical no-write gate fires (SPEC §10, §14 row 27; root rule 2).

Root rule 2 — never write to Databricks, Unity Catalog or a source S3 prefix —
used to be enforced by review alone. Two mechanisms now enforce it, and both are
exercised here against source that must be rejected *and* against the real tree,
which must stay clean:

* `policies/nowrite.semgrep.yml` — call sites (`write_deltalake`,
  `DeltaTable.merge/update/delete/vacuum/restore`, Spark writes whose target
  resolves to a source URI, Databricks SQL outside `discover.py`/`profile.py`,
  S3 writes keyed from a source path);
* `policies/.importlinter` — module boundaries.

semgrep is not a project dependency (it is LGPL-2.1 and only ever invoked as a
subprocess), so it is located on PATH or run through `uvx`; the tests skip with a
clear reason if neither is available.
"""

from __future__ import annotations

import configparser
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEMGREP_RULES = PROJECT_ROOT / "policies" / "nowrite.semgrep.yml"
IMPORTLINTER_CONFIG = PROJECT_ROOT / "policies" / ".importlinter"


def _semgrep_command() -> list[str]:
    direct = shutil.which("semgrep")
    if direct is not None:
        return [direct]
    uvx = shutil.which("uvx")
    if uvx is not None:
        return [uvx, "semgrep"]
    pytest.skip("semgrep unavailable: install it or provide uvx")


def _semgrep_findings(source: str, filename: str = "probe.py") -> set[str]:
    """Rule ids that fire on `source`."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / filename
        probe.write_text(textwrap.dedent(source), encoding="utf-8")
        result = subprocess.run(
            [*_semgrep_command(), "--quiet", "--config", str(SEMGREP_RULES), "--json", str(probe)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            check=False,
        )
    payload = json.loads(result.stdout or "{}")
    assert not payload.get("errors"), payload.get("errors")
    return {finding["check_id"].split(".")[-1] for finding in payload.get("results", [])}


# --------------------------------------------------------------------------- #
# semgrep — call sites
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("rule_id", "source"),
    [
        (
            "no-write-deltalake",
            """
            import deltalake
            def f(df, path):
                deltalake.write_deltalake(path, df)
            """,
        ),
        (
            "no-delta-table-mutation",
            """
            def f(delta_table, updates):
                delta_table.merge(updates)
            """,
        ),
        (
            "no-spark-write-to-source",
            """
            def f(df, source_location):
                df.writeTo(source_location)
            """,
        ),
        (
            "no-databricks-sql-outside-discovery",
            """
            def f(cursor, query):
                cursor.execute(query)
            """,
        ),
        (
            "no-write-mode-on-source-path",
            """
            def f(client, source_key):
                client.put_object(Bucket="b", Key=source_key, Body=b"x")
            """,
        ),
    ],
    ids=[
        "write_deltalake",
        "delta-mutation",
        "spark-write-to-source",
        "databricks-sql",
        "s3-write-to-source",
    ],
)
def test_semgrep_rule_fires(rule_id: str, source: str) -> None:
    assert rule_id in _semgrep_findings(source)


def test_databricks_sql_is_allowed_in_discover() -> None:
    """The rule excludes the two modules SPEC §10 permits."""
    source = """
    def f(cursor, query):
        cursor.execute(query)
    """
    assert "no-databricks-sql-outside-discovery" not in _semgrep_findings(source, "discover.py")


def test_semgrep_is_clean_on_the_real_tree() -> None:
    result = subprocess.run(
        [
            *_semgrep_command(),
            "--quiet",
            "--config",
            str(SEMGREP_RULES),
            "--error",
            "src",
            "spark_jobs",
            "tools",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# import-linter — module boundaries
# --------------------------------------------------------------------------- #


def _lint_imports(
    config: Path, cwd: Path, extra_path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    import os

    env = dict(os.environ)
    paths = [str(PROJECT_ROOT / "src")]
    if extra_path is not None:
        paths.insert(0, str(extra_path))
    env["PYTHONPATH"] = os.pathsep.join(paths)
    executable = shutil.which("lint-imports")
    if executable is None:  # pragma: no cover - import-linter is a dev dependency
        pytest.skip("lint-imports not on PATH")
    return subprocess.run(
        [executable, "--config", str(config)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def test_importlinter_contracts_hold_on_the_real_package() -> None:
    result = _lint_imports(IMPORTLINTER_CONFIG, PROJECT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 broken" in result.stdout


def test_importlinter_forbidden_modules_match_the_spec() -> None:
    """The contracts ban what SPEC §10 names, not something weaker."""
    parser = configparser.ConfigParser()
    parser.read(IMPORTLINTER_CONFIG)

    databricks = parser["importlinter:contract:databricks-sql-confined"]
    assert "databricks" in databricks["forbidden_modules"]
    assert "table_mcp.discover" in databricks["ignore_imports"]
    assert "table_mcp.profile" in databricks["ignore_imports"]

    delta = parser["importlinter:contract:no-delta-writer-in-conversion"]
    assert "deltalake" in delta["forbidden_modules"]
    for module in ("table_mcp.convert", "table_mcp.promote", "table_mcp.glue"):
        assert module in delta["source_modules"]


def test_importlinter_contract_fires_on_a_violating_package(tmp_path: Path) -> None:
    """A probe package that imports a forbidden module must break the contract.

    The probe reuses the forbidden module named by the real config, so this
    proves the production contract shape rejects a violation rather than merely
    that import-linter works.
    """
    parser = configparser.ConfigParser()
    parser.read(IMPORTLINTER_CONFIG)
    forbidden = parser["importlinter:contract:no-delta-writer-in-conversion"][
        "forbidden_modules"
    ].strip()

    package = tmp_path / "probe_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "convert.py").write_text(f"import {forbidden}\n", encoding="utf-8")

    config = tmp_path / ".importlinter"
    config.write_text(
        "[importlinter]\n"
        "root_package = probe_pkg\n"
        "include_external_packages = True\n\n"
        "[importlinter:contract:probe]\n"
        "name = probe may not import the forbidden module\n"
        "type = forbidden\n"
        "source_modules =\n    probe_pkg.convert\n"
        f"forbidden_modules =\n    {forbidden}\n",
        encoding="utf-8",
    )

    result = _lint_imports(config, tmp_path, extra_path=tmp_path)
    assert result.returncode != 0, result.stdout
    assert "1 broken" in result.stdout
