"""Deny-by-default role and scope authorization (SEC-02, specs/06-security.md section 4)."""

from __future__ import annotations

from enum import StrEnum

from abm.application.caller import CallerContext
from abm.domain.results import Failure, failure


class Operation(StrEnum):
    """Authorized operations by API id. Health (API-20, API-21) is unauthenticated and not listed."""

    REGISTER_ACCOUNT = "API-01"
    READ_ACCOUNT = "API-02"
    READ_HISTORY = "API-03"
    INCOMING_ACH_CREATE = "API-04"
    INCOMING_ACH_SETTLE = "API-05"
    INCOMING_ACH_RETURN = "API-06"
    OUTGOING_ACH_CREATE = "API-07"
    OUTGOING_ACH_SUBMIT = "API-08"
    OUTGOING_ACH_SETTLE = "API-09"
    OUTGOING_ACH_REJECT = "API-10"
    OUTGOING_ACH_CANCEL = "API-11"
    INTERNAL_TRANSFER = "API-12"
    CARD_AUTHORIZE = "API-13"
    CARD_CLEAR = "API-14"
    CARD_REVERSE = "API-15"
    CORRECTION = "API-16"
    RISK_RESTRICTION = "API-17"
    CLOSE_ACCOUNT = "API-18"
    RECONCILIATION_TRACE = "API-19"
    OUTGOING_ACH_RETURN = "API-22"
    CARD_EXPIRE = "API-23"
    CARD_REFUND = "API-24"
    LEGAL_HOLD = (
        "LEGAL-HOLD"  # non-public retention_controller port, not an HTTP operation
    )


O = Operation

# One row per role, exactly as the authorization matrix in specs/06-security.md section 4.
PERMISSIONS: dict[str, frozenset[Operation]] = {
    "account_registrar": frozenset({O.REGISTER_ACCOUNT, O.CLOSE_ACCOUNT}),
    "account_reader": frozenset({O.READ_ACCOUNT, O.READ_HISTORY}),
    "payment_orchestrator": frozenset(
        {
            O.INCOMING_ACH_CREATE,
            O.INCOMING_ACH_SETTLE,
            O.INCOMING_ACH_RETURN,
            O.OUTGOING_ACH_CREATE,
            O.OUTGOING_ACH_SUBMIT,
            O.OUTGOING_ACH_SETTLE,
            O.OUTGOING_ACH_REJECT,
            O.OUTGOING_ACH_CANCEL,
            O.INTERNAL_TRANSFER,
            O.OUTGOING_ACH_RETURN,
        }
    ),
    "card_orchestrator": frozenset(
        {O.CARD_AUTHORIZE, O.CARD_CLEAR, O.CARD_REVERSE, O.CARD_EXPIRE, O.CARD_REFUND}
    ),
    "correction_authority": frozenset({O.CORRECTION}),
    "risk_controller": frozenset({O.RISK_RESTRICTION}),
    "reconciliation_reader": frozenset({O.RECONCILIATION_TRACE}),
    "retention_controller": frozenset({O.LEGAL_HOLD}),
}
ACCOUNT_SCOPED = frozenset({O.READ_ACCOUNT, O.READ_HISTORY})


def authorize(
    caller: CallerContext, operation: Operation, account_id: str | None = None
) -> Failure | None:
    """None when permitted. Pure and database-free, so it runs before any write transaction.

    Unknown role, another role's operation, a missing or different account scope, and an
    account-scoped read with no target account are all the same generic denial, so a caller
    learns nothing about which check failed.
    """
    denied = failure("FORBIDDEN_SCOPE", "The caller is not permitted to do this.")
    if operation not in PERMISSIONS.get(caller.role, frozenset()):
        return denied
    if operation in ACCOUNT_SCOPED and (
        account_id is None or caller.account_scope != account_id
    ):
        return denied
    return None
