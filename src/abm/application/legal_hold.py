"""Account-level legal hold set or clear by retention_controller (FR-16, DEC-0010, DEC-0012).

A non-public port: no HTTP route exposes it. The hold covers the account and every dependent
retained record, and it blocks retention eligibility. ABM validates and records the opaque
instruction; it never decides the hold.
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

OPERATION = "legal_hold"
_FIELDS = frozenset(
    {"instruction_id", "record_type", "record_id", "action", "decision_reference"}
)


def set_legal_hold(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.LEGAL_HOLD)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        parsed = to_fields(body, _FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        if parsed["record_type"] != "account" or parsed["record_id"] != target:
            raise InvalidValue("legal hold targets the account itself")
        action = parsed["action"]
        if action not in ("set", "clear"):
            raise InvalidValue("action is not set or clear")
        decision = opaque_id(parsed["decision_reference"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        retention = tx.get_retention(target)
        if retention is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        # the requested state must differ from the current one (as for API-17)
        if (action == "set") == retention.legal_hold:
            return failure(
                "INVALID_TRANSITION", "The legal hold is already in that state."
            )
        held = action == "set"
        tx.set_legal_hold(target, held, decision if held else None)
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
        return Success(Response(200, {"account_id": target, "legal_hold": held}))

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
                "record_type": "account",
                "record_id": target,
                "action": action,
                "decision_reference": decision,
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )
