"""Internal transfer: one atomic debit and equal credit between two open accounts (FR-06, API-12).

The transfer completes immediately. The source must be unblocked and hold enough available funds.
Both ledger effects, both balances, the movement, and the trace are written in one transaction.
"""

from __future__ import annotations

from abm.application.ach import amount as to_cents
from abm.application.ach import fields as to_fields
from abm.application.ach import ledger_id
from abm.application.authorization import Operation, authorize
from abm.application.caller import CallerContext
from abm.application.idempotency import Response, run_idempotent, scope_key
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

OPERATION = "internal_transfer"
_FIELDS = frozenset(
    {
        "instruction_id",
        "movement_id",
        "source_account_id",
        "destination_account_id",
        "amount_cents",
        "currency",
    }
)


def _balances(account_id: str, account: AccountSnapshot) -> dict[str, object]:
    return {
        "account_id": account_id,
        "current_balance_cents": account.current_balance_cents,
        "held_balance_cents": account.held_balance_cents,
        "available_balance_cents": account.current_balance_cents
        - account.held_balance_cents,
    }


def internal_transfer(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.INTERNAL_TRANSFER)
    if denied is not None:
        return denied
    try:
        parsed = to_fields(body, _FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        movement_id = opaque_id(parsed["movement_id"])
        source = opaque_id(parsed["source_account_id"])
        destination = opaque_id(parsed["destination_account_id"])
        cents = to_cents(parsed["amount_cents"])
        require_usd(parsed["currency"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")
    if source == destination:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        src = tx.account_snapshot(source)
        dst = tx.account_snapshot(destination)
        if src is None or dst is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        if src.status != "open" or dst.status != "open":
            return failure("ACCOUNT_CLOSED", "The account is closed.")
        if src.restriction != "none":
            return failure(
                "OUTGOING_BLOCKED", "Outgoing activity is blocked for this account."
            )
        if tx.get_movement(movement_id) is not None:
            return failure("INVALID_TRANSITION", "The movement already exists.")
        if src.current_balance_cents - src.held_balance_cents < cents:
            return failure("INSUFFICIENT_FUNDS", "The available balance is not enough.")

        debit = ledger_id(movement_id, "transfer_source_debit")
        credit = ledger_id(movement_id, "transfer_destination_credit")
        tx.create_movement(
            NewMovement(
                movement_id,
                source,
                OPERATION,
                "completed",
                cents,
                None,
                None,
                destination,
            ),
            now,
        )
        tx.post_ledger(
            LedgerPost(
                debit,
                source,
                movement_id,
                "transfer_source_debit",
                "debit",
                cents,
                caller.caller_id,
                caller.role,
                None,
            ),
            now,
        )
        tx.post_ledger(
            LedgerPost(
                credit,
                destination,
                movement_id,
                "transfer_destination_credit",
                "credit",
                cents,
                caller.caller_id,
                caller.role,
                None,
            ),
            now,
        )
        tx.apply_balance(source, -cents)
        tx.apply_balance(destination, cents)
        tx.append_trace(
            TraceEntry(
                account_id=source,
                instruction_id=instruction_id,
                operation=OPERATION,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
                movement_id=movement_id,
                ledger_entry_id=debit,
                movement_state="completed",
            )
        )
        after_src = AccountSnapshot(
            src.status,
            src.current_balance_cents - cents,
            src.held_balance_cents,
            src.restriction,
        )
        after_dst = AccountSnapshot(
            dst.status,
            dst.current_balance_cents + cents,
            dst.held_balance_cents,
            dst.restriction,
        )
        data = {
            "movement_id": movement_id,
            "movement_type": OPERATION,
            "state": "completed",
            "accounts": [
                _balances(source, after_src),
                _balances(destination, after_dst),
            ],
        }
        return Success(Response(201, data))

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(source, OPERATION),
        key=key,
        fingerprint=fingerprint(
            OPERATION,
            {
                "instruction_id": instruction_id,
                "movement_id": movement_id,
                "source_account_id": source,
                "destination_account_id": destination,
                "amount_cents": cents,
                "currency": "USD",
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )
