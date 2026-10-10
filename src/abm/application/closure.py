"""Account closure: eligible open account becomes terminal (INV-15, FR-14, API-18).

Closure needs zero current balance, no active hold, and no unresolved movement (DEC-0044). The
restriction does not block closure (DEC-0042 and API-18). A closed account never reopens.
"""

from __future__ import annotations

from abm.application.ach import fields as to_fields
from abm.application.authorization import Operation, authorize
from abm.application.caller import CallerContext
from abm.application.idempotency import Response, run_idempotent, scope_key
from abm.application.retention import finalize
from abm.domain.errors import InvalidValue
from abm.domain.fingerprint import fingerprint
from abm.domain.identifiers import opaque_id
from abm.domain.results import Result, Success, failure
from abm.ports.clock import Clock
from abm.ports.storage import TraceEntry, UnitOfWork, WriteTransaction

OPERATION = "close_account"
_FIELDS = frozenset({"instruction_id"})


def close_account(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.CLOSE_ACCOUNT)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        parsed = to_fields(body, _FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        if account.status == "closed":
            return failure("INVALID_TRANSITION", "The account is already closed.")
        if account.current_balance_cents != 0 or tx.has_open_obligation(target):
            return failure(
                "CLOSURE_PRECONDITION_FAILED",
                "The account cannot be closed while it has balance or open activity.",
            )
        tx.close_account(target, now)
        tx.append_trace(
            TraceEntry(
                account_id=target,
                instruction_id=instruction_id,
                operation=OPERATION,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
            )
        )
        finalize(tx, target, now)
        return Success(Response(200, {"account_id": target, "status": "closed"}))

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, OPERATION),
        key=key,
        fingerprint=fingerprint(
            OPERATION, {"instruction_id": instruction_id, "account_id": target}
        ),
        instruction_id=instruction_id,
        work=work,
    )
