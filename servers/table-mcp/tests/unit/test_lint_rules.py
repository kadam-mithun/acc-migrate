"""The three logging-discipline rules actually fail the build (OPEN_QUESTIONS #11).

SPEC §10 requires that all log emission pass through `redact.py`. The allow-list
in `redact.redact_event` enforces that for structured keys; these three rules
close the routes around it:

    (a) `print`                     — ruff T201
    (b) stdlib `logging`            — ruff TID251 (banned-api)
    (c) non-static event strings    — tools/check_log_calls.py

A rule that is configured but not firing is worse than no rule, so each is
exercised against source that must be rejected, and against source that must be
accepted.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = PROJECT_ROOT / "tools" / "check_log_calls.py"

# A filename inside the package, so ruff resolves this project's pyproject.toml.
PROBE_FILENAME = "src/table_mcp/_probe.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_log_calls", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_log_calls"] = module
    spec.loader.exec_module(module)
    return module


def _ruff(source: str) -> str:
    ruff = shutil.which("ruff")
    if ruff is None:  # pragma: no cover - ruff is a dev dependency
        pytest.skip("ruff not on PATH")
    result = subprocess.run(
        [ruff, "check", "--no-cache", "--stdin-filename", PROBE_FILENAME, "-"],
        input=source,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# (a) print
# --------------------------------------------------------------------------- #


def test_rule_a_print_is_rejected() -> None:
    assert "T201" in _ruff('print("trade_date=2026-01-01")\n')


def test_rule_a_allows_the_sanctioned_logger() -> None:
    clean = 'from table_mcp.redact import get_logger\n\nget_logger("x").info("staged")\n'
    assert "T201" not in _ruff(clean)


# --------------------------------------------------------------------------- #
# (b) stdlib logging
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "source",
    [
        "import logging\n",
        "import logging.config\n",
        "from logging import getLogger\n",
    ],
    ids=["import", "submodule", "from-import"],
)
def test_rule_b_stdlib_logging_is_rejected(source: str) -> None:
    assert "TID251" in _ruff(source)


def test_rule_b_allows_structlog_through_redact() -> None:
    assert "TID251" not in _ruff("from table_mcp.redact import get_logger\n")


def test_rule_b_exempts_only_redact_itself() -> None:
    """redact.py imports the level constant; nothing else may import logging."""
    ruff = shutil.which("ruff")
    if ruff is None:  # pragma: no cover - ruff is a dev dependency
        pytest.skip("ruff not on PATH")
    result = subprocess.run(
        [ruff, "check", "--no-cache", "--stdin-filename", "src/table_mcp/redact.py", "-"],
        input="import logging\n",
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert "TID251" not in result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# (c) non-static event strings
# --------------------------------------------------------------------------- #

BAD_EVENTS = [
    ('log.info(f"staged {table}")', "LOG001"),
    ('log.info("staged %s" % table)', "LOG002"),
    ('log.info("staged {}".format(table))', "LOG003"),
    ('log.info("staged " + table)', "LOG004"),
]


@pytest.mark.parametrize(
    ("statement", "code"), BAD_EVENTS, ids=["f-string", "percent", "format", "concat"]
)
def test_rule_c_non_static_event_is_rejected(statement: str, code: str) -> None:
    checker = _load_checker()
    source = f'log = get_logger("x")\n{statement}\n'
    violations = checker.check_source(source, "probe.py")
    assert [v.code for v in violations] == [code], statement


@pytest.mark.parametrize("method", ["debug", "info", "warning", "error", "critical", "exception"])
def test_rule_c_covers_every_log_method(method: str) -> None:
    checker = _load_checker()
    source = f'log = get_logger("x")\nlog.{method}(f"staged {{table}}")\n'
    assert len(checker.check_source(source, "probe.py")) == 1


def test_rule_c_accepts_a_static_event_with_keyword_arguments() -> None:
    checker = _load_checker()
    source = (
        'log = get_logger("x")\n'
        'log.info("table staged", run_id=run_id, row_count=n, file_set_hash=h)\n'
    )
    assert checker.check_source(source, "probe.py") == []


def test_rule_c_follows_loggers_bound_from_get_logger() -> None:
    """A logger under any name is still a logger."""
    checker = _load_checker()
    source = 'audit = get_logger("x")\naudit.info(f"staged {table}")\n'
    assert len(checker.check_source(source, "probe.py")) == 1


def test_rule_c_ignores_unrelated_objects() -> None:
    """`response.info(...)` is not a log call."""
    checker = _load_checker()
    assert checker.check_source('response.info(f"{x}")\n', "probe.py") == []


def test_rule_c_cli_exits_non_zero_and_reports_the_line(tmp_path: Path) -> None:
    offending = tmp_path / "bad.py"
    offending.write_text('log = get_logger("x")\nlog.info(f"staged {table}")\n', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "LOG001" in result.stderr
    assert "bad.py:2:1" in result.stderr


def test_rule_c_cli_passes_on_this_repo() -> None:
    """The rule is live against the real source tree, not only fixtures."""
    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "src", "spark_jobs", "tests"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
