#!/usr/bin/env bash
# Auto-format and lint after edits; non-blocking.
command -v ruff >/dev/null 2>&1 || exit 0
ruff format --quiet . 2>/dev/null || true
ruff check --quiet . 2>/dev/null || true
exit 0
