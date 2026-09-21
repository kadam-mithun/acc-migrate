"""Domain exceptions (SPEC §13, §14 row 25).

The raise-side pair of :class:`~table_mcp.schemas.ErrorEnvelope`. SPEC §3 names
the codes a caller must be able to act on — `APPROVAL_REQUIRED` (AT-13),
`APPROVAL_INVALID`, `ALREADY_PROMOTED`, `LOCKED` (AT-12), `KMS_KEY_REQUIRED`
(AT-15), `WRITE_GRANT_PRESENT` (AT-14) — and §14 row 25 makes it normative that
they keep their identity and never collapse into `INTERNAL`.

`server._dispatch` maps :class:`TableMcpError` ahead of its generic branch, so
raising one of these is how a domain module refuses.

The message is authored here, never taken from a library, so it is safe to log
as-is; a wrapped third-party exception goes through `redact.py` instead.
"""

from __future__ import annotations

from table_mcp.schemas import ErrorCode

__all__ = [
    "AlreadyPromotedError",
    "ApprovalInvalidError",
    "ApprovalRequiredError",
    "KmsKeyRequiredError",
    "LockedError",
    "TableMcpError",
    "WriteGrantPresentError",
]


class TableMcpError(Exception):
    """A refusal or failure that already knows its `ErrorCode`."""

    code: ErrorCode = ErrorCode.INTERNAL

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        retryable: bool = False,
        table: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.retryable = retryable
        self.table = table
        self.hint = hint


class ApprovalRequiredError(TableMcpError):
    """No approval record for the given id (SPEC §9.1, AT-13)."""

    code = ErrorCode.APPROVAL_REQUIRED


class ApprovalInvalidError(TableMcpError):
    """An approval record exists but a field does not match (SPEC §9.1)."""

    code = ErrorCode.APPROVAL_INVALID


class AlreadyPromotedError(TableMcpError):
    """`force` may not re-convert a PROMOTED table (SPEC §3, §9)."""

    code = ErrorCode.ALREADY_PROMOTED


class LockedError(TableMcpError):
    """Another run holds a live lease on the table (SPEC §9, AT-12)."""

    code = ErrorCode.LOCKED


class KmsKeyRequiredError(TableMcpError):
    """No `options.kms_key_arn`; refused before any S3 write (SPEC §10, AT-15)."""

    code = ErrorCode.KMS_KEY_REQUIRED


class WriteGrantPresentError(TableMcpError):
    """The service principal holds a write grant on source (SPEC §10, AT-14)."""

    code = ErrorCode.WRITE_GRANT_PRESENT
