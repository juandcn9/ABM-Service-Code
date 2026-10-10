"""Incoming ACH: notice, settlement, and one full return (FR-02, FR-03; API-04, API-05, API-06).

A notice creates a pending movement with no balance effect. Valid settlement evidence posts one
credit and settles the movement. Only after settlement, one full return equal to that credit posts
one debit and may make the balance negative (INV-10). Each step is one write transaction.
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

NOTICE = "create_incoming_ach"
SETTLE = "settle_incoming_ach"
RETURN = "return_incoming_ach"
_NOTICE_FIELDS = frozenset(
    {"instruction_id", "movement_id", "amount_cents", "currency", "external_reference"}
)
_SETTLE_FIELDS = frozenset({"instruction_id", "evidence_reference"})
_RETURN_FIELDS = frozenset(
    {"instruction_id", "evidence_reference", "amount_cents", "currency"}
)


def create_incoming_ach(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.INCOMING_ACH_CREATE)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        fields = to_fields(body, _NOTICE_FIELDS)
        instruction_id = opaque_id(fields["instruction_id"])
        movement_id = opaque_id(fields["movement_id"])
        amount = to_cents(fields["amount_cents"])
        require_usd(fields["currency"])
        external_reference = opaque_id(fields["external_reference"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        if account.status != "open":
            return failure("ACCOUNT_CLOSED", "The account is closed.")
        if tx.get_movement(movement_id) is not None:
            return failure("INVALID_TRANSITION", "The movement already exists.")
        tx.create_movement(
            NewMovement(
                movement_id,
                target,
                "incoming_ach",
                "pending",
                amount,
                external_reference,
            ),
            now,
        )
        tx.append_trace(
            TraceEntry(
                account_id=target,
                instruction_id=instruction_id,
                operation=NOTICE,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
                movement_id=movement_id,
                movement_state="pending",
                external_reference=external_reference,
            )
        )
        return Success(
            Response(
                201,
                movement_data(movement_id, "incoming_ach", "pending", target, account),
            )
        )

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, NOTICE),
        key=key,
        fingerprint=fingerprint(
            NOTICE,
            {
                "account_id": target,
                "movement_id": movement_id,
                "instruction_id": instruction_id,
                "amount_cents": amount,
                "currency": "USD",
                "external_reference": external_reference,
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )


def settle_incoming_ach(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    movement_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.INCOMING_ACH_SETTLE)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        movement = opaque_id(movement_id)
        fields = to_fields(body, _SETTLE_FIELDS)
        instruction_id = opaque_id(fields["instruction_id"])
        evidence = opaque_id(fields["evidence_reference"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        if account.status != "open":
            return failure("ACCOUNT_CLOSED", "The account is closed.")
        record = tx.get_movement(movement)
        if (
            record is None
            or record.account_id != target
            or record.movement_type != "incoming_ach"
        ):
            return failure("MOVEMENT_NOT_FOUND", "The movement was not found.")
        if record.state != "pending":
            return failure("INVALID_TRANSITION", "The movement is not pending.")
        if tx.evidence_reference_taken(evidence):
            return failure(
                "INVALID_TRANSITION", "The evidence reference was already used."
            )
        credit = ledger_id(movement, "incoming_settlement")
        tx.add_evidence(evidence, movement, "settlement", now)
        tx.post_ledger(
            LedgerPost(
                entry_id=credit,
                account_id=target,
                movement_id=movement,
                effect_kind="incoming_settlement",
                direction="credit",
                amount_cents=record.amount_cents,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                external_reference=record.external_reference,
            ),
            now,
        )
        tx.apply_balance(target, record.amount_cents)
        tx.set_movement_state(movement, "settled", now)
        tx.append_trace(
            TraceEntry(
                account_id=target,
                instruction_id=instruction_id,
                operation=SETTLE,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                correlation_id=caller.correlation_id,
                occurred_at=now,
                movement_id=movement,
                ledger_entry_id=credit,
                evidence_reference=evidence,
                movement_state="settled",
                external_reference=record.external_reference,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents + record.amount_cents,
            account.held_balance_cents,
        )
        return Success(
            Response(
                200, movement_data(movement, "incoming_ach", "settled", target, after)
            )
        )

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, SETTLE),
        key=key,
        fingerprint=fingerprint(
            SETTLE,
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


def return_incoming_ach(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    movement_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.INCOMING_ACH_RETURN)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        movement = opaque_id(movement_id)
        fields = to_fields(body, _RETURN_FIELDS)
        instruction_id = opaque_id(fields["instruction_id"])
        evidence = opaque_id(fields["evidence_reference"])
        amount = to_cents(fields["amount_cents"])
        require_usd(fields["currency"])
        key = opaque_id(idempotency_key)
    except InvalidValue:
        return failure("VALIDATION_ERROR", "The request is not valid.")

    def work(tx: WriteTransaction, now: str) -> Result[Response]:
        account = tx.account_snapshot(target)
        if account is None:
            return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
        # a closed account may still receive its return (INV-16, permitted late evidence)
        record = tx.get_movement(movement)
        if (
            record is None
            or record.account_id != target
            or record.movement_type != "incoming_ach"
        ):
            return failure("MOVEMENT_NOT_FOUND", "The movement was not found.")
        if record.state != "settled":
            return failure(
                "INVALID_TRANSITION", "Only a settled movement can be returned."
            )
        if amount != record.amount_cents:
            return failure(
                "AMOUNT_MISMATCH", "The return must equal the settled amount."
            )
        if tx.evidence_reference_taken(evidence):
            return failure(
                "INVALID_TRANSITION", "The evidence reference was already used."
            )
        debit = ledger_id(movement, "incoming_return")
        tx.add_evidence(evidence, movement, "return", now)
        tx.post_ledger(
            LedgerPost(
                entry_id=debit,
                account_id=target,
                movement_id=movement,
                effect_kind="incoming_return",
                direction="debit",
                amount_cents=record.amount_cents,
                caller_id=caller.caller_id,
                caller_role=caller.role,
                external_reference=record.external_reference,
            ),
            now,
        )
        tx.apply_balance(target, -record.amount_cents)
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
                ledger_entry_id=debit,
                evidence_reference=evidence,
                movement_state="returned",
                external_reference=record.external_reference,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents - record.amount_cents,
            account.held_balance_cents,
        )
        finalize(tx, target, now)
        return Success(
            Response(
                200, movement_data(movement, "incoming_ach", "returned", target, after)
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
                "amount_cents": amount,
                "currency": "USD",
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )
