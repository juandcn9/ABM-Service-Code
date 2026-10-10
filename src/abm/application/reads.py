"""Account, history, and reconciliation-trace reads (FR-11, FR-12, FR-13; API-02, API-03, API-19).

Reads never mutate, store no idempotency outcome, and run inside one consistent snapshot, so
balances, holds, and trace pages are mutually consistent (BT-04, BT-05, INV-05).
"""

from __future__ import annotations

from abm.application.authorization import Operation, authorize
from abm.application.caller import CallerContext
from abm.application.idempotency import Response
from abm.domain.errors import InvalidValue
from abm.domain.identifiers import opaque_id
from abm.domain.results import Result, Success, failure
from abm.ports.storage import StorageFailure, TraceRow, UnitOfWork

MAX_HISTORY_LIMIT = 200
MAX_CURSOR = 2**63 - 1  # the largest SQLite INTEGER; larger values cannot be bound
DEFAULT_HISTORY_LIMIT = 50
MAX_TRACE_LIMIT = 1000
DEFAULT_TRACE_LIMIT = 100

_INVALID = failure("VALIDATION_ERROR", "The request is not valid.")


def _count(value: object, minimum: int, maximum: int | None = None) -> int:
    """A query integer: a real int (not bool) within bounds."""
    if (
        type(value) is not int
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        raise InvalidValue("query value out of range")
    return value


def get_account(
    uow: UnitOfWork, caller: CallerContext, account_id: object
) -> Result[Response]:
    """Lifecycle, restriction, posted/held/available balances, and active holds (API-02)."""
    try:
        target = opaque_id(account_id)
    except InvalidValue:
        return _INVALID
    denied = authorize(caller, Operation.READ_ACCOUNT, target)
    if denied is not None:
        return denied
    try:
        with uow.read() as tx:
            account = tx.get_account(target)
    except StorageFailure as exc:
        return exc.failure
    if account is None:
        return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
    held = sum(hold.amount_cents for hold in account.active_holds)
    return Success(
        Response(
            200,
            {
                "account_id": account.account_id,
                "currency": "USD",
                "status": account.status,
                "restriction": account.restriction,
                "balances": {
                    "account_id": account.account_id,
                    "current_balance_cents": account.current_balance_cents,
                    "held_balance_cents": held,
                    "available_balance_cents": account.current_balance_cents - held,
                },
                "active_holds": [
                    {
                        "hold_id": h.hold_id,
                        "movement_id": h.movement_id,
                        "amount_cents": h.amount_cents,
                        "state": h.state,
                    }
                    for h in account.active_holds
                ],
            },
        )
    )


def get_history(
    uow: UnitOfWork,
    caller: CallerContext,
    account_id: object,
    after_sequence: object = 0,
    limit: object = DEFAULT_HISTORY_LIMIT,
) -> Result[Response]:
    """Retained ledger entries in stable sequence order, with a bounded cursor (API-03)."""
    try:
        target = opaque_id(account_id)
        after = _count(after_sequence, 0, MAX_CURSOR)
        size = _count(limit, 1, MAX_HISTORY_LIMIT)
    except InvalidValue:
        return _INVALID
    denied = authorize(caller, Operation.READ_HISTORY, target)
    if denied is not None:
        return denied
    try:
        with uow.read() as tx:
            if tx.get_account(target) is None:
                return failure("ACCOUNT_NOT_FOUND", "The account was not found.")
            # one extra row marks another page
            rows = tx.history_page(target, after, size + 1)
    except StorageFailure as exc:
        return exc.failure
    page = rows[:size]
    return Success(
        Response(
            200,
            {
                "account_id": target,
                "items": [
                    {
                        "sequence": r.sequence,
                        "entry_id": r.entry_id,
                        "movement_id": r.movement_id,
                        "effect_kind": r.effect_kind,
                        "direction": r.direction,
                        "amount_cents": r.amount_cents,
                        "currency": "USD",
                        "created_at": r.created_at,
                    }
                    for r in page
                ],
                "next_after_sequence": page[-1].sequence if len(rows) > size else None,
            },
        )
    )


def _trace_item(row: TraceRow) -> dict[str, object]:
    return {
        "sequence": row.sequence,
        "account_id": row.account_id,
        "instruction_id": row.instruction_id,
        "movement_id": row.movement_id,
        "operation": row.operation,
        "caller_id": row.caller_id,
        "caller_role": row.caller_role,
        "correlation_id": row.correlation_id,
        "occurred_at": row.occurred_at,
        "ledger_entry_id": row.ledger_entry_id,
        "movement_state": row.movement_state,
        "effect_kind": row.effect_kind,
        "direction": row.direction,
        "amount_cents": row.amount_cents,
        "currency": "USD" if row.ledger_entry_id is not None else None,
        "evidence_reference": row.evidence_reference,
        "external_reference": row.external_reference,
    }


def get_trace(
    uow: UnitOfWork,
    caller: CallerContext,
    after_sequence: object = 0,
    limit: object = DEFAULT_TRACE_LIMIT,
    cutoff_sequence: object = None,
) -> Result[Response]:
    """One page of the reconciliation trace bounded by an inclusive cutoff (API-19).

    The first page (no cutoff) captures the highest committed sequence; every later page echoes
    it, so records committed after the first page never appear in the same walk.
    """
    denied = authorize(caller, Operation.RECONCILIATION_TRACE)
    if denied is not None:
        return denied
    try:
        after = _count(after_sequence, 0, MAX_CURSOR)
        size = _count(limit, 1, MAX_TRACE_LIMIT)
        requested = (
            None if cutoff_sequence is None else _count(cutoff_sequence, 0, MAX_CURSOR)
        )
    except InvalidValue:
        return _INVALID
    try:
        with uow.read() as tx:
            current = tx.trace_cutoff()
            if requested is not None and requested > current:
                # a cutoff beyond the committed end could later admit records into a finished walk
                return _INVALID
            cutoff = current if requested is None else requested
            rows = tx.trace_page(after, cutoff, size + 1)
    except StorageFailure as exc:
        return exc.failure
    page = rows[:size]
    return Success(
        Response(
            200,
            {
                "cutoff_sequence": cutoff,
                "items": [_trace_item(r) for r in page],
                "next_after_sequence": page[-1].sequence if len(rows) > size else None,
            },
        )
    )
