"""Outgoing ACH: accept with a hold, submit, settle or reject or cancel, and one full return (API-07..11, API-22).

Acceptance requires available funds and creates one active hold. Settlement posts one debit and
finalizes the hold in the same transaction. Rejection and cancellation release the hold without a
debit. Only after settlement, one full return equal to that debit posts one credit. Every state
change is one write transaction with an idempotent outcome.
"""

from __future__ import annotations

from collections.abc import Callable

from abm.application.ach import amount as to_cents
from abm.application.ach import fields as to_fields
from abm.application.ach import hold_id, ledger_id, movement_data
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
    MovementRecord,
    NewMovement,
    TraceEntry,
    UnitOfWork,
    WriteTransaction,
)

CREATE = "create_outgoing_ach"
SUBMIT = "submit_outgoing_ach"
SETTLE = "settle_outgoing_ach"
REJECT = "reject_outgoing_ach"
CANCEL = "cancel_outgoing_ach"
RETURN = "return_outgoing_ach"
_CREATE_FIELDS = frozenset(
    {
        "instruction_id",
        "movement_id",
        "amount_cents",
        "currency",
        "external_reference",
        "destination_reference",
    }
)
_EVIDENCE_FIELDS = frozenset({"instruction_id", "evidence_reference"})
_RETURN_FIELDS = frozenset(
    {"instruction_id", "evidence_reference", "amount_cents", "currency"}
)


def _record_for(
    tx: WriteTransaction, account_id: str, movement_id: str
) -> MovementRecord | None:
    record = tx.get_movement(movement_id)
    if (
        record is None
        or record.account_id != account_id
        or record.movement_type != "outgoing_ach"
    ):
        return None
    return record


def create_outgoing_ach(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.OUTGOING_ACH_CREATE)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        parsed = to_fields(body, _CREATE_FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        movement_id = opaque_id(parsed["movement_id"])
        cents = to_cents(parsed["amount_cents"])
        require_usd(parsed["currency"])
        external_reference = opaque_id(parsed["external_reference"])
        destination = opaque_id(parsed["destination_reference"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        if account.status != "open":
            return failure("ACCOUNT_CLOSED", "The account is closed.")
        if account.restriction != "none":
            return failure(
                "OUTGOING_BLOCKED", "Outgoing activity is blocked for this account."
            )
        if tx.get_movement(movement_id) is not None:
            return failure("INVALID_TRANSITION", "The movement already exists.")
        available = account.current_balance_cents - account.held_balance_cents
        if available < cents:
            return failure("INSUFFICIENT_FUNDS", "The available balance is not enough.")
        tx.create_movement(
            NewMovement(
                movement_id,
                target,
                "outgoing_ach",
                "accepted_with_hold",
                cents,
                external_reference,
                destination,
            ),
            now,
        )
        tx.create_hold(hold_id(movement_id), movement_id, target, cents, now)
        tx.append_trace(
            TraceEntry(
                account_id=target,
                instruction_id=instruction_id,
                operation=CREATE,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
                movement_id=movement_id,
                movement_state="accepted_with_hold",
                external_reference=external_reference,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents,
            account.held_balance_cents + cents,
            account.restriction,
        )
        data = movement_data(
            movement_id, "outgoing_ach", "accepted_with_hold", target, after
        )
        return Success(Response(201, data))

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, CREATE),
        key=key,
        fingerprint=fingerprint(
            CREATE,
            {
                "account_id": target,
                "movement_id": movement_id,
                "instruction_id": instruction_id,
                "amount_cents": cents,
                "currency": "USD",
                "external_reference": external_reference,
                "destination_reference": destination,
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )


def _evidence_transition(
    operation: str,
    permission: Operation,
    required_state: str,
    evidence_kind: str,
    new_state: str,
    settle: bool,
    closes_hold: bool,
) -> Callable[..., Result[Response]]:
    """One evidence-driven transition. Submission keeps the hold; the others end it."""

    def command(
        uow: UnitOfWork,
        clock: Clock,
        caller: CallerContext,
        idempotency_key: object,
        account_id: object,
        movement_id: object,
        body: object,
    ) -> Result[Response]:
        denied = authorize(caller, permission)
        if denied is not None:
            return denied
        try:
            target = opaque_id(account_id)
            movement = opaque_id(movement_id)
            parsed = to_fields(body, _EVIDENCE_FIELDS)
            instruction_id = opaque_id(parsed["instruction_id"])
            evidence = opaque_id(parsed["evidence_reference"])
            key = opaque_id(idempotency_key)
        except InvalidValue:
            return failure("VALIDATION_ERROR", "The request is not valid.")

        def work(tx: WriteTransaction, now: str) -> Result[Response]:
            account = tx.account_snapshot(target)
            if account is None:
                return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
            record = _record_for(tx, target, movement)
            if record is None:
                return failure("MOVEMENT_NOT_FOUND", "The movement was not found.")
            if record.state != required_state:
                return failure(
                    "INVALID_TRANSITION", "The movement is not in the required state."
                )
            if closes_hold and tx.hold_state(movement) != "active":
                # checked before any write: a refused call must move no money
                return failure("INVALID_TRANSITION", "The movement has no active hold.")
            if tx.evidence_reference_taken(evidence):
                return failure(
                    "INVALID_TRANSITION", "The evidence reference was already used."
                )
            tx.add_evidence(evidence, movement, evidence_kind, now)
            current, held = account.current_balance_cents, account.held_balance_cents
            ledger = None
            if settle:
                ledger = ledger_id(movement, "outgoing_settlement")
                tx.post_ledger(
                    LedgerPost(
                        entry_id=ledger,
                        account_id=target,
                        movement_id=movement,
                        effect_kind="outgoing_settlement",
                        direction="debit",
                        amount_cents=record.amount_cents,
                        caller_id=caller.caller_id,
                        caller_role=caller.role,
                        external_reference=record.external_reference,
                    ),
                    now,
                )
                tx.apply_balance(target, -record.amount_cents)
                current -= record.amount_cents
            if closes_hold:
                # the hold leaves the active set: posted on settlement, released otherwise
                tx.finalize_hold(
                    movement, "posted" if settle else "released", evidence, now
                )
                held -= record.amount_cents
            tx.set_movement_state(movement, new_state, now)
            tx.append_trace(
                TraceEntry(
                    account_id=target,
                    instruction_id=instruction_id,
                    operation=operation,
                    caller_id=caller.caller_id,
                    caller_role=caller.role,
                    correlation_id=caller.correlation_id,
                    occurred_at=now,
                    movement_id=movement,
                    ledger_entry_id=ledger,
                    evidence_reference=evidence,
                    movement_state=new_state,
                    external_reference=record.external_reference,
                )
            )
            after = AccountSnapshot(account.status, current, held, account.restriction)
            data = movement_data(movement, "outgoing_ach", new_state, target, after)
            return Success(Response(200, data))

        return run_idempotent(
            uow,
            clock,
            scope=scope_key(target, operation),
            key=key,
            fingerprint=fingerprint(
                operation,
                {
                    "account_id": target,
                    "movement_id": movement,
                    "instruction_id": instruction_id,
                    "evidence_reference": evidence,
                },
            ),
            instruction_id=instruction_id,
            work=work,
        )

    return command


submit_outgoing_ach = _evidence_transition(
    SUBMIT,
    Operation.OUTGOING_ACH_SUBMIT,
    "accepted_with_hold",
    "submission",
    "submitted",
    settle=False,
    closes_hold=False,
)
settle_outgoing_ach = _evidence_transition(
    SETTLE,
    Operation.OUTGOING_ACH_SETTLE,
    "submitted",
    "settlement",
    "settled",
    settle=True,
    closes_hold=True,
)
reject_outgoing_ach = _evidence_transition(
    REJECT,
    Operation.OUTGOING_ACH_REJECT,
    "submitted",
    "rejection",
    "rejected",
    settle=False,
    closes_hold=True,
)
cancel_outgoing_ach = _evidence_transition(
    CANCEL,
    Operation.OUTGOING_ACH_CANCEL,
    "accepted_with_hold",
    "cancellation",
    "cancelled_before_submission",
    settle=False,
    closes_hold=True,
)


def return_outgoing_ach(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    movement_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.OUTGOING_ACH_RETURN)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        movement = opaque_id(movement_id)
        parsed = to_fields(body, _RETURN_FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        evidence = opaque_id(parsed["evidence_reference"])
        cents = to_cents(parsed["amount_cents"])
        require_usd(parsed["currency"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        record = _record_for(tx, target, movement)
        if record is None:
            return failure("MOVEMENT_NOT_FOUND", "The movement was not found.")
        if record.state != "settled":
            return failure(
                "INVALID_TRANSITION", "Only a settled movement can be returned."
            )
        if cents != record.amount_cents:
            return failure(
                "AMOUNT_MISMATCH", "The return must equal the settled amount."
            )
        if tx.evidence_reference_taken(evidence):
            return failure(
                "INVALID_TRANSITION", "The evidence reference was already used."
            )
        credit = ledger_id(movement, "outgoing_return")
        tx.add_evidence(evidence, movement, "return", now)
        tx.post_ledger(
            LedgerPost(
                entry_id=credit,
                account_id=target,
                movement_id=movement,
                effect_kind="outgoing_return",
                direction="credit",
                amount_cents=record.amount_cents,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                external_reference=record.external_reference,
            ),
            now,
        )
        tx.apply_balance(target, record.amount_cents)
        tx.set_movement_state(movement, "returned", now)
        tx.append_trace(
            TraceEntry(
                account_id=target,
                instruction_id=instruction_id,
                operation=RETURN,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
                movement_id=movement,
                ledger_entry_id=credit,
                evidence_reference=evidence,
                movement_state="returned",
                external_reference=record.external_reference,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents + record.amount_cents,
            account.held_balance_cents,
            account.restriction,
        )
        return Success(
            Response(
                200, movement_data(movement, "outgoing_ach", "returned", target, after)
            )
        )

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, RETURN),
        key=key,
        fingerprint=fingerprint(
            RETURN,
            {
                "account_id": target,
                "movement_id": movement,
                "instruction_id": instruction_id,
                "evidence_reference": evidence,
                "amount_cents": cents,
                "currency": "USD",
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )
