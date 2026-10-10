"""Outgoing risk restriction set or clear, decided externally (FR-10, API-17).

Only risk_controller may set or clear the block. The change has no balance effect. A set block
is enforced by outgoing ACH, internal transfer and card authorization (INV-11); it does not stop
incoming credit, returns, reversals or approved corrections.
"""

from __future__ import annotations

from abm.application.ach import fields as to_fields
from abm.application.authorization import Operation, authorize
from abm.application.caller import CallerContext
from abm.application.idempotency import Response, run_idempotent, scope_key
from abm.domain.errors import InvalidValue
from abm.domain.fingerprint import fingerprint
from abm.domain.identifiers import opaque_id
from abm.domain.results import Result, Success, failure
from abm.ports.clock import Clock
from abm.ports.storage import TraceEntry, UnitOfWork, WriteTransaction

OPERATION = "risk_restriction"
_FIELDS = frozenset({"instruction_id", "action", "decision_reference"})
_BLOCKED = "outgoing_blocked"


def set_risk_restriction(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.RISK_RESTRICTION)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        parsed = to_fields(body, _FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        action = parsed["action"]
        if action not in ("set", "clear"):
            raise InvalidValue("action is not set or clear")
        decision = opaque_id(parsed["decision_reference"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        # the requested state must differ from the current one (API-17 prerequisite)
        if (action == "set") == (account.restriction == _BLOCKED):
            return failure(
                "INVALID_TRANSITION", "The restriction is already in that state."
            )

        new_restriction = _BLOCKED if action == "set" else "none"
        tx.set_restriction(
            target, new_restriction, decision if action == "set" else None
        )
        tx.append_trace(
            TraceEntry(
                account_id=target,
                instruction_id=instruction_id,
                operation=OPERATION,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
                external_reference=decision,
            )
        )
        return Success(
            Response(200, {"account_id": target, "restriction": new_restriction})
        )

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, OPERATION),
        key=key,
        fingerprint=fingerprint(
            OPERATION,
            {
                "instruction_id": instruction_id,
                "account_id": target,
                "action": action,
                "decision_reference": decision,
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )
