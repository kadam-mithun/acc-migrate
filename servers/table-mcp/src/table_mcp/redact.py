"""Redaction layer (SPEC §10).

All log emission passes through this module: :func:`configure_logging` installs
:func:`redact_event` as the last processor before the renderer, and
:func:`get_logger` is the only sanctioned way to obtain a logger. A key reaches
the output only if :data:`LOGGABLE_KEYS` or :data:`LOGGABLE_SUFFIXES` admits it —
an allow-list, so a new field is dropped until someone decides it is safe, rather
than logged until someone notices it is not.

Responsibilities per the spec:

* partition paths are logged with partition *values* replaced by a stable hash
  (`trade_date=<h:8f3a>`);
* exceptions from PySpark, delta-rs, PyIceberg and Pydantic are wrapped in an
  :class:`~table_mcp.schemas.ErrorEnvelope` with the library message scrubbed of
  quoted literals and path values before logging;
* Pydantic validation errors report field names only.

AT-18 is the acceptance test: a forced PySpark exception carrying a literal must
produce an envelope with no quoted literals and no partition values.
"""

from __future__ import annotations

import logging
import re
from typing import cast

import structlog
from pydantic import ValidationError
from structlog.typing import EventDict, FilteringBoundLogger, WrappedLogger

from table_mcp.errors import TableMcpError
from table_mcp.schemas import TABLE_FQN_PATTERN, ErrorCode, ErrorEnvelope

__all__ = [
    "LOGGABLE_KEYS",
    "LOGGABLE_SUFFIXES",
    "configure_logging",
    "domain_error_envelope",
    "get_logger",
    "hash_value",
    "redact_event",
    "redact_message",
    "redact_path",
    "safe_table_tag",
    "to_error_envelope",
    "validation_error_envelope",
]

_TABLE_FQN_RE = re.compile(TABLE_FQN_PATTERN)

# Keys whose values are identifiers, counts, hashes, durations or codes — the
# things SPEC §10 says logs may carry. Everything else is dropped.
#
# Deliberately absent: `path`, `location`, `prefix`, `uri`, `metadata_location`
# and friends. SPEC §10 allows *redacted* paths, and a path still carries
# partition values until :func:`redact_path` exists; admit them here only once it
# does. Also absent: `exc_info` and `exception`, so a traceback or a raw library
# message can never be rendered — exceptions become an `ErrorEnvelope` instead.
LOGGABLE_KEYS: frozenset[str] = frozenset(
    {
        # structlog's own
        "event",
        "level",
        "timestamp",
        "logger",
        "logger_name",
        # correlation
        "run_id",
        "plan_id",
        "table",
        "table_ref",
        "tool",
        "attempt",
        "engine",
        # decisions and outcomes
        "strategy",
        "rule_id",
        "state",
        "code",
        "decision",
        "retryable",
        "matched",
        "truncated",
        "force",
        "warnings",
        "warning",
        # measurements
        "count",
        "bytes",
        "duration",
        "elapsed",
        # bookkeeping added by this module
        "redacted_keys",
    }
)

# Suffix rules, so a new measurement or identifier does not need an entry each
# time: `file_count`, `emr_job_run_id`, `file_set_hash`, `duration_ms`,
# `size_bytes`, `delta_version`.
LOGGABLE_SUFFIXES: tuple[str, ...] = (
    "_count",
    "_id",
    "_hash",
    "_ms",
    "_bytes",
    "_version",
    "_seconds",
)


def _is_loggable(key: str) -> bool:
    """True when the allow-list admits `key`."""
    return key in LOGGABLE_KEYS or key.endswith(LOGGABLE_SUFFIXES)


def redact_event(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """structlog processor: drop every key the allow-list does not admit.

    Dropped keys are reported by **name only** under `redacted_keys`, so an
    operator can see that something was withheld and add it to
    :data:`LOGGABLE_KEYS` deliberately — the value never reaches the renderer.

    This cannot police the `event` string itself: an f-string built from a column
    value would still leak. Event strings must be static, with the variable parts
    passed as keyword arguments so they meet this allow-list. OPEN_QUESTIONS #11
    tracks the lint rule that enforces that and bans `print`/stdlib `logging`.
    """
    kept: EventDict = {key: value for key, value in event_dict.items() if _is_loggable(key)}
    dropped = sorted(key for key in event_dict if key not in kept)
    if dropped:
        kept["redacted_keys"] = dropped
    return kept


def configure_logging(*, level: int = logging.INFO) -> None:
    """Install the structured logging chain (SPEC §10).

    :func:`redact_event` sits last before the renderer, so it sees every key any
    earlier processor added. `structlog.processors.format_exc_info` is
    deliberately **not** in the chain: rendering a traceback would put raw
    PySpark, delta-rs and PyIceberg messages into the log, which is exactly what
    `ErrorEnvelope` exists to prevent.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_event,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """Return the module's logger. The only sanctioned way to log in this server."""
    return cast(FilteringBoundLogger, structlog.get_logger(name))


def safe_table_tag(table: str | None) -> str | None:
    """Return `table` only if it is a well-formed FQN, else None.

    `ErrorEnvelope.table` is pattern-constrained, so an odd identifier would make
    building the envelope raise from inside the error path and let the original
    exception escape unredacted. Dropping the tag is always safer than raising.
    """
    if table is None or _TABLE_FQN_RE.match(table) is None:
        return None
    return table


def hash_value(value: str) -> str:
    """Return the stable short hash used in place of a data value (`<h:8f3a>`)."""
    raise NotImplementedError("SPEC §10 — redaction layer")


def redact_path(path: str) -> str:
    """Replace partition values in an S3/table path with stable hashes."""
    raise NotImplementedError("SPEC §10 — redaction layer")


def redact_message(message: str) -> str:
    """Scrub quoted literals and path values from a library exception message."""
    raise NotImplementedError("SPEC §10 — redaction layer")


def validation_error_envelope(
    exc: ValidationError,
    *,
    code: ErrorCode = ErrorCode.INTERNAL,
    table: str | None = None,
) -> ErrorEnvelope:
    """Wrap a Pydantic validation failure, reporting **field names only**.

    SPEC §10: "Pydantic validation errors report field names only." Pydantic puts
    the rejected value in `input` and interpolates it into `msg`, so only `loc`
    (the field path) and `type` (a stable code such as `string_too_short`) are
    read here — never `input`, `msg`, `str(exc)` or the traceback.
    """
    fields = sorted(
        {".".join(str(part) for part in error["loc"]) or "<root>" for error in exc.errors()}
    )
    codes = sorted({str(error["type"]) for error in exc.errors()})
    return ErrorEnvelope(
        code=code,
        message=f"input validation failed for field(s): {', '.join(fields)}",
        retryable=False,
        table=safe_table_tag(table),
        hint=f"constraint(s): {', '.join(codes)}",
    )


def domain_error_envelope(exc: TableMcpError) -> ErrorEnvelope:
    """Envelope for an error that already carries its `ErrorCode` (SPEC §3).

    The message is ours, not a library's, so it passes through unscrubbed and the
    spec-named refusals keep their codes — `APPROVAL_REQUIRED`, `LOCKED`,
    `ALREADY_PROMOTED`, `KMS_KEY_REQUIRED`, `WRITE_GRANT_PRESENT`.
    """
    return ErrorEnvelope(
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        table=safe_table_tag(exc.table),
        hint=exc.hint,
    )


def to_error_envelope(
    exc: BaseException,
    *,
    code: ErrorCode = ErrorCode.INTERNAL,
    table: str | None = None,
) -> ErrorEnvelope:
    """Wrap an exception as a redacted `ErrorEnvelope` (SPEC §3, §10).

    Until :func:`redact_message` is implemented the envelope carries the
    exception *class name* only. That is the no-side-effect option of root rule
    1: it cannot leak a literal, and it keeps the scaffold from shipping a weak
    scrubber that looks finished. AT-18 drives the full implementation, after
    which the scrubbed message is substituted here.
    """
    return ErrorEnvelope(
        code=code,
        message=f"{type(exc).__name__} (message withheld pending SPEC §10 scrubbing)",
        retryable=False,
        table=safe_table_tag(table),
        hint="See the conversion record for redacted detail.",
    )
