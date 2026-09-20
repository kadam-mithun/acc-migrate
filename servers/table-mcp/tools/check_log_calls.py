#!/usr/bin/env python3
"""Fail the build on a non-static log event string (SPEC §10, OPEN_QUESTIONS #11).

`redact.redact_event` is an allow-list over the *structured* keys of a log
record, so it can guarantee that no unapproved keyword argument reaches the
renderer. It cannot see inside the event string: ::

    log.info(f"staged {partition_value}")   # leaks, invisibly to the allow-list
    log.info("staged", partition_hash=h)    # allow-list applies

This check closes that gap. It flags an f-string, `%` formatting, `.format()` or
`+` concatenation used as the **first positional argument** to a logger method.

The two companion rules are expressible in ruff and configured in
`pyproject.toml`: `T20` bans `print`, and `TID251` bans the stdlib `logging`
module. This one is not, which is why it lives here.

Scope: attribute calls whose receiver is a name bound from `get_logger(...)` in
the same module, or one of :data:`DEFAULT_LOGGER_NAMES`. A dynamic string held
in a variable (`msg = f"..."; log.info(msg)`) is not detectable statically and
remains a review matter.

Usage::

    python tools/check_log_calls.py src spark_jobs
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

LOG_METHODS: frozenset[str] = frozenset(
    {"debug", "info", "warning", "warn", "error", "critical", "exception", "msg", "log"}
)

DEFAULT_LOGGER_NAMES: frozenset[str] = frozenset({"log", "logger", "_log", "_logger", "LOG"})

LOGGER_FACTORIES: frozenset[str] = frozenset({"get_logger", "bind"})

SKIP_DIRS: frozenset[str] = frozenset(
    {".venv", "__pycache__", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
)


@dataclass(frozen=True)
class Violation:
    """One non-static event string."""

    path: Path
    line: int
    column: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.code} {self.message}"


def _classify(node: ast.expr) -> tuple[str, str] | None:
    """Return `(code, message)` when `node` is a non-static string expression."""
    if isinstance(node, ast.JoinedStr):
        return ("LOG001", "f-string as log event; use a static event and keyword arguments")
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mod):
            return ("LOG002", "%-formatted log event; use a static event and keyword arguments")
        if isinstance(node.op, ast.Add):
            return ("LOG004", "concatenated log event; use a static event and keyword arguments")
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    ):
        return ("LOG003", ".format() log event; use a static event and keyword arguments")
    return None


def _logger_names(tree: ast.AST) -> set[str]:
    """Names bound from a logger factory, plus the conventional ones."""
    names = set(DEFAULT_LOGGER_NAMES)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if called in LOGGER_FACTORIES:
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return names


def check_source(source: str, path: Path | str = "<string>") -> list[Violation]:
    """Return every non-static log event string in `source`."""
    path = Path(path)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # a file ruff/mypy will reject anyway
        return [Violation(path, exc.lineno or 0, exc.offset or 0, "LOG000", "syntax error")]

    names = _logger_names(tree)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LOG_METHODS:
            continue
        receiver = node.func.value
        if not isinstance(receiver, ast.Name) or receiver.id not in names:
            continue
        if not node.args:
            continue
        found = _classify(node.args[0])
        if found is not None:
            code, message = found
            violations.append(Violation(path, node.lineno, node.col_offset + 1, code, message))
    return violations


def check_path(root: Path) -> list[Violation]:
    """Check one file, or every `.py` file under a directory."""
    if root.is_file():
        return check_source(root.read_text(encoding="utf-8"), root)
    violations: list[Violation] = []
    for file in sorted(root.rglob("*.py")):
        if SKIP_DIRS.intersection(file.parts):
            continue
        violations.extend(check_source(file.read_text(encoding="utf-8"), file))
    return violations


def main(argv: list[str]) -> int:
    """Exit non-zero when any target holds a non-static log event string."""
    targets = [Path(arg) for arg in argv[1:]] or [Path("src")]
    violations: list[Violation] = []
    for target in targets:
        if target.exists():
            violations.extend(check_path(target))

    for violation in violations:
        sys.stderr.write(f"{violation}\n")
    if violations:
        count = len(violations)
        sys.stderr.write(
            f"\n{count} non-static log event string(s). "
            "The redaction allow-list cannot see inside an event string: pass a static "
            "event and put the variable parts in keyword arguments (SPEC §10).\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
