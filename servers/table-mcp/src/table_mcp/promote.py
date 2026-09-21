"""Promotion (SPEC §3 `promote_table`, §9.1).

L1 — human approval required. **Any PR touching this file needs two human
reviewers** (root CLAUDE.md rule 2; add the `needs-two-reviewers` label).

The promotion gate of SPEC §9.1 is normative: the ledger must hold an approval
record with `approval_id`, `table_ref` equal, `plan_id` equal to the plan that
staged the table, `recon_record_id` referencing a `recon-mcp` record with
`status = PASS` for the same table and staged snapshot id, `approver`,
`approved_at` and `decision = APPROVE`.

Missing or unknown `approval_id` → `APPROVAL_REQUIRED` (AT-13); a record that is
present but mismatched in any field → `APPROVAL_INVALID`.
"""

from __future__ import annotations

from table_mcp.errors import ApprovalInvalidError, ApprovalRequiredError
from table_mcp.schemas import ApprovalRecord, PromoteTableInput, PromoteTableOutput


def validate_approval(
    approval: ApprovalRecord | None,
    *,
    table_fqn: str,
    plan_id: str,
    staged_snapshot_id: int | None,
) -> None:
    """Enforce the SPEC §9.1 gate.

    Raises :class:`~table_mcp.errors.ApprovalRequiredError` when the record is
    missing or unknown (AT-13), and
    :class:`~table_mcp.errors.ApprovalInvalidError` on any field mismatch. Both
    keep their code through `server._dispatch` (SPEC §14 row 25).
    """
    _ = (ApprovalRequiredError, ApprovalInvalidError)  # the refusals this gate raises
    raise NotImplementedError("SPEC §9.1 promotion gate")


def promote_table(params: PromoteTableInput) -> PromoteTableOutput:
    """Move a staged table to the production database and prefix, after the gate."""
    raise NotImplementedError("SPEC §3 promote_table")
