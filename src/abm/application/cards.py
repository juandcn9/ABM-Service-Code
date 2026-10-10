"""Card: authorization with hold, clearing, reversal, expiry, late clearing, and one full refund (FR-07, FR-08).

Authorization requires available funds and creates one active hold. Clearing from an authorization
posts its evidence-backed amount and posts the hold in the same transaction (the final amount may
differ). Reversal and expiry release the hold without posting. A late clearing after reversal or
expiry posts one debit without a hold and never reopens an account. One full refund equal to the
clearing debit follows clearing (INV-10, specs/02 section 5).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from abm.application.ach import amount as to_cents
from abm.application.ach import fields as to_fields
from abm.application.ach import hold_id, ledger_id, movement_data
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
    MovementRecord,
    NewMovement,
    TraceEntry,
    UnitOfWork,
    WriteTransaction,
)

AUTHORIZE = "authorize_card"
CLEAR = "clear_card"
REVERSE = "reverse_card"
EXPIRE = "expire_card"
REFUND = "refund_card"
_AUTHORIZE_FIELDS = frozenset(
    {
        "instruction_id",
        "movement_id",
        "amount_cents",
        "currency",
        "external_reference",
        "merchant_reference",
    }
)
_CLEARING_FIELDS = frozenset(
    {"instruction_id", "evidence_reference", "amount_cents", "currency"}
)
_EVIDENCE_FIELDS = frozenset({"instruction_id", "evidence_reference"})
_REFUND_FIELDS = frozenset(
    {"instruction_id", "evidence_reference", "amount_cents", "currency"}
)


def _card(
    tx: WriteTransaction, account_id: str, movement_id: str
) -> MovementRecord | None:
    record = tx.get_movement(movement_id)
    if (
        record is None
        or record.account_id != account_id
        or record.movement_type != "card"
    ):
        return None
    return record


def _trace(
    caller: CallerContext,
    account_id: str,
    instruction_id: str,
    operation: str,
    now: str,
    movement_id: str,
    state: str,
    external_reference: str | None,
    ledger: str | None = None,
    evidence: str | None = None,
) -> TraceEntry:
    return TraceEntry(
        account_id=account_id,
        instruction_id=instruction_id,
        operation=operation,
        caller_id=caller.caller_id,
        caller_role=caller.role,
        correlation_id=caller.correlation_id,
        occurred_at=now,
        movement_id=movement_id,
        ledger_entry_id=ledger,
        evidence_reference=evidence,
        movement_state=state,
        external_reference=external_reference,
    )


def authorize_card(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.CARD_AUTHORIZE)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        parsed = to_fields(body, _AUTHORIZE_FIELDS)
        instruction_id = opaque_id(parsed["instruction_id"])
        movement_id = opaque_id(parsed["movement_id"])
        cents = to_cents(parsed["amount_cents"])
        require_usd(parsed["currency"])
        external_reference = opaque_id(parsed["external_reference"])
        merchant = opaque_id(parsed["merchant_reference"])
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
        if account.current_balance_cents - account.held_balance_cents < cents:
            return failure("INSUFFICIENT_FUNDS", "The available balance is not enough.")
        tx.create_movement(
            NewMovement(
                movement_id,
                target,
                "card",
                "authorized_with_hold",
                cents,
                external_reference,
                None,
                None,
                merchant,
            ),
            now,
        )
        tx.create_hold(hold_id(movement_id), movement_id, target, cents, now)
        tx.append_trace(
            _trace(
                caller,
                target,
                instruction_id,
                AUTHORIZE,
                now,
                movement_id,
                "authorized_with_hold",
                external_reference,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents,
            account.held_balance_cents + cents,
            account.restriction,
        )
        return Success(
            Response(
                201,
                movement_data(
                    movement_id, "card", "authorized_with_hold", target, after
                ),
            )
        )

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, AUTHORIZE),
        key=key,
        fingerprint=fingerprint(
            AUTHORIZE,
            {
                "account_id": target,
                "movement_id": movement_id,
                "instruction_id": instruction_id,
                "amount_cents": cents,
                "currency": "USD",
                "external_reference": external_reference,
                "merchant_reference": merchant,
            },
        ),
        instruction_id=instruction_id,
        work=work,
    )


def clear_card(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    movement_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.CARD_CLEAR)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        movement = opaque_id(movement_id)
        parsed = to_fields(body, _CLEARING_FIELDS)
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
        record = _card(tx, target, movement)
        if record is None:
            return failure("MOVEMENT_NOT_FOUND", "The movement was not found.")
        if record.state not in ("authorized_with_hold", "reversed", "expired"):
            return failure(
                "INVALID_TRANSITION",
                "The card movement cannot be cleared in its state.",
            )
        if tx.evidence_reference_taken(evidence):
            return failure(
                "INVALID_TRANSITION", "The evidence reference was already used."
            )
        authorized = record.state == "authorized_with_hold"
        new_state = "cleared" if authorized else "late_cleared"
        debit = ledger_id(movement, "card_clearing")
        tx.add_evidence(evidence, movement, "clearing", now)
        tx.post_ledger(
            LedgerPost(
                debit,
                target,
                movement,
                "card_clearing",
                "debit",
                cents,
                caller.caller_id,
                caller.role,
                record.external_reference,
            ),
            now,
        )
        tx.apply_balance(target, -cents)
        held = account.held_balance_cents
        if authorized:
            # the hold is posted in the same transaction; a late clearing has no hold to move
            tx.finalize_hold(movement, "posted", evidence, now)
            held -= record.amount_cents
        tx.set_movement_state(movement, new_state, now)
        tx.append_trace(
            _trace(
                caller,
                target,
                instruction_id,
                CLEAR,
                now,
                movement,
                new_state,
                record.external_reference,
                debit,
                evidence,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents - cents,
            held,
            account.restriction,
        )
        finalize(tx, target, now)
        return Success(
            Response(200, movement_data(movement, "card", new_state, target, after))
        )

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, CLEAR),
        key=key,
        fingerprint=fingerprint(
            CLEAR,
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


def _release(
    operation: str,
    permission: Operation,
    evidence_kind: str,
    new_state: str,
) -> Callable[..., Result[Response]]:
    """Reversal or expiry: release the hold without posting, from an authorization only."""

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
            record = _card(tx, target, movement)
            if record is None:
                return failure("MOVEMENT_NOT_FOUND", "The movement was not found.")
            if record.state != "authorized_with_hold":
                return failure(
                    "INVALID_TRANSITION", "Only an authorization can be released."
                )
            if tx.evidence_reference_taken(evidence):
                return failure(
                    "INVALID_TRANSITION", "The evidence reference was already used."
                )
            tx.add_evidence(evidence, movement, evidence_kind, now)
            tx.finalize_hold(movement, "released", evidence, now)
            tx.set_movement_state(movement, new_state, now)
            tx.append_trace(
                _trace(
                    caller,
                    target,
                    instruction_id,
                    operation,
                    now,
                    movement,
                    new_state,
                    record.external_reference,
                    None,
                    evidence,
                )
            )
            after = AccountSnapshot(
                account.status,
                account.current_balance_cents,
                account.held_balance_cents - record.amount_cents,
                account.restriction,
            )
            return Success(
                Response(200, movement_data(movement, "card", new_state, target, after))
            )

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


reverse_card = _release(REVERSE, Operation.CARD_REVERSE, "reversal", "reversed")
expire_card = _release(EXPIRE, Operation.CARD_EXPIRE, "expiration", "expired")


def refund_card(
    uow: UnitOfWork,
    clock: Clock,
    caller: CallerContext,
    idempotency_key: object,
    account_id: object,
    movement_id: object,
    body: object,
) -> Result[Response]:
    denied = authorize(caller, Operation.CARD_REFUND)
    if denied is not None:
        return denied
    try:
        target = opaque_id(account_id)
        movement = opaque_id(movement_id)
        parsed: Mapping[str, object] = to_fields(body, _REFUND_FIELDS)
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
        record = _card(tx, target, movement)
        if record is None:
            return failure("MOVEMENT_NOT_FOUND", "The movement was not found.")
        if record.state not in ("cleared", "late_cleared"):
            return failure(
                "INVALID_TRANSITION", "Only a cleared card movement can be refunded."
            )
        clearing = tx.ledger_amount(movement, "card_clearing")
        if clearing is None or cents != clearing:
            return failure(
                "AMOUNT_MISMATCH", "The refund must equal the clearing debit."
            )
        if tx.evidence_reference_taken(evidence):
            return failure(
                "INVALID_TRANSITION", "The evidence reference was already used."
            )
        credit = ledger_id(movement, "card_refund")
        tx.add_evidence(evidence, movement, "refund", now)
        tx.post_ledger(
            LedgerPost(
                credit,
                target,
                movement,
                "card_refund",
                "credit",
                cents,
                caller.caller_id,
                caller.role,
                record.external_reference,
            ),
            now,
        )
        tx.apply_balance(target, cents)
        tx.set_movement_state(movement, "refunded", now)
        tx.append_trace(
            _trace(
                caller,
                target,
                instruction_id,
                REFUND,
                now,
                movement,
                "refunded",
                record.external_reference,
                credit,
                evidence,
            )
        )
        after = AccountSnapshot(
            account.status,
            account.current_balance_cents + cents,
            account.held_balance_cents,
            account.restriction,
        )
        finalize(tx, target, now)
        return Success(
            Response(200, movement_data(movement, "card", "refunded", target, after))
        )

    return run_idempotent(
        uow,
        clock,
        scope=scope_key(target, REFUND),
        key=key,
        fingerprint=fingerprint(
            REFUND,
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
