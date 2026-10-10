"""Approved correction: one append-only entry linked to an external decision (FR-09, API-16).

The correction authority decides; ABM appends the entry once. The original entry, movement and
trace stay unchanged. A correction is accepted while a risk restriction is set and may make the
current balance negative (INV-10). Closure is TASK-21, so closed accounts are not checked here.
"""

from __future__ import annotations

from abm.application.ach import amount as to_cents
from abm.application.ach import fields as to_fields
from abm.application.ach import ledger_id, movement_data
from abm.application.authorization import Operation, authorize
from abm.application.caller import CallerContext
from abm.application.idempotency import Response, run_idempotent, scope_key
from abm.application.retention import finalize
from abm.domain.errors import InvalidValue
from abm.domain.fingerprint import fingerprint
from abm.domain.identifiers import opaque_id
from abm.domain.money import require_usd
from abm.domain.results import Result, Success, failure
from abm.ports.clock import Clock
from abm.ports.storage import (
    AccountSnapshot,
    LedgerPost,
    NewMovement,
    TraceEntry,
    UnitOfWork,
    WriteTransaction,
)

OPERATION = "correction"
_FIELDS = frozenset(
    {
        "instruction_id",
        "correction_id",
        "direction",
        "amount_cents",
        "currency",
        "decision_reference",
        "corrected_entry_reference",
    }
)
_DIRECTIONS = frozenset({"credit", "debit"})


def create_correction(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.CORRECTION)
    if denied is not None:
        return denied
    # corrected_entry_reference is optional in the contract; absent means null
    if type(body) is dict and "corrected_entry_reference" not in body:
        body = {**body, "corrected_entry_reference": None}
    try:
        target = opaque_id(account_id)
        parsed = to_fields(body, _FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        correction_id = opaque_id(parsed["correction_id"])
        direction = parsed["direction"]
        if direction not in _DIRECTIONS:
            raise InvalidValue("direction is not credit or debit")
        cents = to_cents(parsed["amount_cents"])
        require_usd(parsed["currency"])
        decision = opaque_id(parsed["decision_reference"])
        corrected = (
            None
            if parsed["corrected_entry_reference"] is None
            else opaque_id(parsed["corrected_entry_reference"])
        )
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        if tx.get_movement(correction_id) is not None:
            return failure("INVALID_TRANSITION", "The correction already exists.")
        if tx.decision_reference_taken(decision):
            return failure(
                "INVALID_TRANSITION", "The decision already has a correction."
            )
        if corrected is not None and tx.ledger_entry_account(corrected) != target:
            return failure("INVALID_TRANSITION", "The corrected entry was not found.")

        entry = ledger_id(correction_id, "correction")
        signed = cents if direction == "credit" else -cents
        tx.create_movement(
            NewMovement(
                correction_id,
                target,
                OPERATION,
                "completed",
                cents,
                None,
                decision_reference=decision,
            ),
            now,
        )
        tx.post_ledger(
            LedgerPost(
                entry,
                target,
                correction_id,
                "correction",
                direction,
                cents,
                caller.caller_id,
                caller.role,
                None,
                corrected,
            ),
            now,
        )
        tx.apply_balance(target, signed)
        tx.append_trace(
            TraceEntry(
                account_id=target,
                instruction_id=instruction_id,
                operation=OPERATION,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
                movement_id=correction_id,
                ledger_entry_id=entry,
                movement_state="completed",
                external_reference=decision,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents + signed,
            account.held_balance_cents,
            account.restriction,
        )
        finalize(tx, target, now)
        return Success(
            Response(
                201,
                movement_data(correction_id, OPERATION, "completed", target, after),
            )
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
                "correction_id": correction_id,
                "account_id": target,
                "direction": direction,
                "amount_cents": cents,
                "currency": "USD",
                "decision_reference": decision,
                "corrected_entry_reference": corrected,
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )
