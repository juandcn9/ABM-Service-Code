"""Outgoing ACH: accept with hold, submit, settle, reject, cancel, and one full return (API-07..11, API-22)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest

from abm.application.caller import CallerContext
from abm.application.idempotency import Response
from abm.application.incoming_ach import (
    create_incoming_ach,
    return_incoming_ach,
    settle_incoming_ach,
)
from abm.application.outgoing_ach import (
    cancel_outgoing_ach,
    create_outgoing_ach,
    reject_outgoing_ach,
    return_outgoing_ach,
    settle_outgoing_ach,
    submit_outgoing_ach,
)
from abm.application.registration import register_account
from abm.domain.results import Failure, Result, Success
from abm.persistence.migrations import load_migrations
from abm.persistence.readiness import readiness_reasons, start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = load_migrations(ROOT / "migrations")
NOW = "2026-10-10T12:00:00Z"
REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
READER = CallerContext("reader-1", "account_reader", "corr-r", "acct-1")


@pytest.fixture
def conn(tmp_path: pathlib.Path) -> sqlite3.Connection:
    started = start_database(tmp_path / "abm.sqlite3", MIGRATIONS, NOW)
    assert started.connection is not None
    return started.connection


@pytest.fixture
def uow(conn: sqlite3.Connection) -> SqliteUnitOfWork:
    return SqliteUnitOfWork(conn)


@pytest.fixture
def clock() -> ControllableClock:
    return ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))


def data_of(result: Result[Response]) -> dict[str, object]:
    assert isinstance(result, Success), result
    return dict(result.value.data)


def funded(uow: SqliteUnitOfWork, clock: ControllableClock, cents: int = 1000) -> None:
    """Register acct-1 and credit it through the incoming ACH path, so the funds are real."""
    body = {
        "instruction_id": "ins-reg",
        "account_id": "acct-1",
        "customer_id": "cust-1",
        "currency": "USD",
        "eligibility_reference": "elig-1",
    }
    assert isinstance(register_account(uow, clock, REGISTRAR, "key-reg", body), Success)
    notice = {
        "instruction_id": "ins-in",
        "movement_id": "mv-in",
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": "ext-in",
    }
    assert isinstance(
        create_incoming_ach(uow, clock, PAYER, "key-in-n", "acct-1", notice), Success
    )
    settled = {"instruction_id": "ins-in-s", "evidence_reference": "ev-in"}
    assert isinstance(
        settle_incoming_ach(uow, clock, PAYER, "key-in-s", "acct-1", "mv-in", settled),
        Success,
    )


def create(uow, clock, movement="mv-out", cents=400, key="key-c", instruction="ins-c"):
    body = {
        "instruction_id": instruction,
        "movement_id": movement,
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": f"ext-{movement}",
        "destination_reference": "dest-1",
    }
    return create_outgoing_ach(uow, clock, PAYER, key, "acct-1", body)


def evidence(fn, uow, clock, movement="mv-out", ref="ev-1", key=None, instruction=None):
    body = {"instruction_id": instruction or f"ins-{ref}", "evidence_reference": ref}
    return fn(uow, clock, PAYER, key or f"key-{ref}", "acct-1", movement, body)


def give_back(uow, clock, movement="mv-out", amount=400, ref="ev-r", key="key-r"):
    body = {
        "instruction_id": f"ins-{ref}",
        "evidence_reference": ref,
        "amount_cents": amount,
        "currency": "USD",
    }
    return return_outgoing_ach(uow, clock, PAYER, key, "acct-1", movement, body)


def balances(conn: sqlite3.Connection) -> tuple[int, int]:
    current = conn.execute("SELECT current_balance_cents FROM accounts").fetchone()[0]
    held = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM holds WHERE state = 'active'"
    ).fetchone()[0]
    return current, held


def counts(conn: sqlite3.Connection) -> tuple[int, ...]:
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "movements",
            "movement_evidence",
            "ledger_entries",
            "audit_trace",
            "holds",
        )
    )


def state(conn: sqlite3.Connection) -> tuple[object, ...]:
    """What a refused call must leave unchanged: balances, holds, movement state, row counts."""
    return (
        balances(conn),
        counts(conn),
        conn.execute(
            "SELECT state FROM movements WHERE movement_id = 'mv-out'"
        ).fetchone(),
        conn.execute(
            "SELECT movement_id, state FROM holds ORDER BY movement_id"
        ).fetchall(),
    )


def test_acceptance_creates_one_active_hold_and_keeps_the_balance(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    data = data_of(create(uow, clock))
    assert data["state"] == "accepted_with_hold"
    assert balances(conn) == (1000, 400)
    assert conn.execute(
        "SELECT destination_reference FROM movements WHERE movement_id = 'mv-out'"
    ).fetchone() == ("dest-1",)
    assert conn.execute(
        "SELECT COUNT(*) FROM ledger_entries WHERE effect_kind = 'outgoing_settlement'"
    ).fetchone() == (0,)


def test_insufficient_funds_is_refused_and_only_the_outcome_is_stored(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock, cents=100)
    before = counts(conn)
    result = create(uow, clock, cents=500)
    assert isinstance(result, Failure) and result.error.code == "INSUFFICIENT_FUNDS"
    assert counts(conn)[:4] == before[:4] and counts(conn)[4] == before[4]


def test_an_existing_hold_reduces_the_funds_available_to_a_new_acceptance(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    assert (
        data_of(
            create(uow, clock, movement="mv-1", cents=600, key="k1", instruction="i1")
        )["state"]
        == "accepted_with_hold"
    )
    before = counts(conn)
    refused = create(uow, clock, movement="mv-2", cents=500, key="k2", instruction="i2")
    assert isinstance(refused, Failure) and refused.error.code == "INSUFFICIENT_FUNDS"
    assert counts(conn) == before
    assert (
        data_of(
            create(uow, clock, movement="mv-3", cents=400, key="k3", instruction="i3")
        )["state"]
        == "accepted_with_hold"
    )


def test_a_restricted_or_closed_account_takes_no_new_outgoing_movement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    conn.execute(
        "UPDATE accounts SET restriction = 'outgoing_blocked', restriction_decision_reference = 'dec-1'"
    )
    before = state(conn)
    blocked = create(uow, clock, movement="mv-b", key="key-b", instruction="ins-b")
    assert isinstance(blocked, Failure) and blocked.error.code == "OUTGOING_BLOCKED"
    assert state(conn) == before
    conn.execute(
        "UPDATE accounts SET restriction = 'none', restriction_decision_reference = NULL"
    )
    conn.execute("UPDATE accounts SET status = 'closed', closed_at = ?", (NOW,))
    before = state(conn)
    closed = create(uow, clock, movement="mv-c", key="key-cl", instruction="ins-cl")
    assert isinstance(closed, Failure) and closed.error.code == "ACCOUNT_CLOSED"
    assert state(conn) == before


def test_a_duplicate_movement_id_under_a_new_key_is_invalid_transition(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    before = state(conn)
    again = create(uow, clock, key="key-dup", instruction="ins-dup")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_submission_keeps_the_hold_active(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    assert data_of(evidence(submit_outgoing_ach, uow, clock))["state"] == "submitted"
    assert balances(conn) == (1000, 400)


def test_settlement_debits_once_and_releases_the_hold_together(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    data = data_of(evidence(settle_outgoing_ach, uow, clock, ref="ev-s"))
    assert data["state"] == "settled"
    assert balances(conn) == (600, 0)
    rows = conn.execute(
        "SELECT effect_kind, direction, amount_cents FROM ledger_entries ORDER BY sequence"
    ).fetchall()
    assert rows == [
        ("incoming_settlement", "credit", 1000),
        ("outgoing_settlement", "debit", 400),
    ]
    assert conn.execute(
        "SELECT state FROM holds WHERE movement_id = 'mv-out'"
    ).fetchone() == ("posted",)


def test_settlement_before_submission_is_refused(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    before = state(conn)
    early = evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    assert isinstance(early, Failure) and early.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_rejection_releases_the_hold_without_a_debit(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    assert (
        data_of(evidence(reject_outgoing_ach, uow, clock, ref="ev-x"))["state"]
        == "rejected"
    )
    assert balances(conn) == (1000, 0)
    assert conn.execute(
        "SELECT COUNT(*) FROM ledger_entries WHERE effect_kind = 'outgoing_settlement'"
    ).fetchone() == (0,)


def test_cancellation_is_allowed_only_before_submission(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    assert (
        data_of(evidence(cancel_outgoing_ach, uow, clock, ref="ev-c"))["state"]
        == "cancelled_before_submission"
    )
    assert balances(conn) == (1000, 0)


def test_a_cancellation_after_submission_is_refused(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    before = state(conn)
    late = evidence(cancel_outgoing_ach, uow, clock, ref="ev-c")
    assert isinstance(late, Failure) and late.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_return_posts_one_full_credit_after_settlement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    assert data_of(give_back(uow, clock))["state"] == "returned"
    assert balances(conn) == (1000, 0)


def test_a_return_must_equal_the_settled_amount_and_follow_settlement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    before = state(conn)
    early = give_back(uow, clock)
    assert isinstance(early, Failure) and early.error.code == "INVALID_TRANSITION"
    assert state(conn) == before
    evidence(submit_outgoing_ach, uow, clock)
    evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    before = state(conn)
    wrong = give_back(uow, clock, amount=399, key="key-r2")
    assert isinstance(wrong, Failure) and wrong.error.code == "AMOUNT_MISMATCH"
    assert state(conn) == before
    assert balances(conn) == (600, 0)


def test_create_replays_the_stored_outcome_without_a_second_hold(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    first = create(uow, clock)
    before = counts(conn)
    second = create(uow, clock)
    assert isinstance(second, Success) and second.replayed is True
    assert second.value == first.value and counts(conn) == before


def test_settling_twice_is_refused_and_changes_nothing(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    before = state(conn)
    again = evidence(settle_outgoing_ach, uow, clock, ref="ev-s2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_rejecting_after_settlement_is_refused_and_changes_nothing(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    before = state(conn)
    late = evidence(reject_outgoing_ach, uow, clock, ref="ev-x")
    assert isinstance(late, Failure) and late.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_cancelling_after_settlement_is_refused_and_changes_nothing(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    before = state(conn)
    late = evidence(cancel_outgoing_ach, uow, clock, ref="ev-c")
    assert isinstance(late, Failure) and late.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_rejecting_before_submission_is_refused_and_changes_nothing(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    before = state(conn)
    early = evidence(reject_outgoing_ach, uow, clock, ref="ev-x")
    assert isinstance(early, Failure) and early.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_a_second_return_is_invalid_transition_with_no_write(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    assert data_of(give_back(uow, clock))["state"] == "returned"
    before = state(conn)
    again = give_back(uow, clock, ref="ev-r2", key="key-r2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_a_return_after_rejection_is_refused_and_changes_nothing(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    evidence(reject_outgoing_ach, uow, clock, ref="ev-x")
    before = state(conn)
    late = give_back(uow, clock)
    assert isinstance(late, Failure) and late.error.code == "INVALID_TRANSITION"
    assert state(conn) == before


def test_a_storage_fault_during_settlement_rolls_everything_back(
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from abm.persistence import sqlite_store

    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    before = counts(conn)
    balance_before = balances(conn)

    def fault(self: object, account_id: str, delta: int) -> None:
        raise sqlite3.OperationalError("injected fault")

    monkeypatch.setattr(sqlite_store.SqliteWriteTransaction, "apply_balance", fault)
    result = evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    assert isinstance(result, Failure)
    assert counts(conn) == before and balances(conn) == balance_before
    assert conn.execute(
        "SELECT state FROM movements WHERE movement_id = 'mv-out'"
    ).fetchone() == ("submitted",)


def test_the_database_is_ready_after_settlement_return_and_a_restart(
    tmp_path: pathlib.Path,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    give_back(uow, clock)
    conn.close()
    reopened = start_database(tmp_path / "abm.sqlite3", MIGRATIONS, NOW)
    assert reopened.ready and reopened.connection is not None
    assert readiness_reasons(reopened.connection, MIGRATIONS) == []


def test_settling_a_reserved_movement_may_leave_the_balance_negative_and_stays_ready(
    tmp_path: pathlib.Path,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    # DEC-0024: the hold reserved the funds at acceptance; an incoming return may then consume them
    funded(uow, clock)
    create(uow, clock, cents=1000)
    evidence(submit_outgoing_ach, uow, clock)
    assert isinstance(
        return_incoming_ach(
            uow,
            clock,
            PAYER,
            "key-in-r",
            "acct-1",
            "mv-in",
            {
                "instruction_id": "ins-in-r",
                "evidence_reference": "ev-in-r",
                "amount_cents": 1000,
                "currency": "USD",
            },
        ),
        Success,
    )
    assert balances(conn) == (0, 1000)
    assert (
        data_of(evidence(settle_outgoing_ach, uow, clock, ref="ev-s"))["state"]
        == "settled"
    )
    assert balances(conn) == (-1000, 0)
    conn.close()
    reopened = start_database(tmp_path / "abm.sqlite3", MIGRATIONS, NOW)
    assert reopened.ready and reopened.connection is not None


def test_a_closing_transition_without_an_active_hold_moves_no_money(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    create(uow, clock)
    evidence(submit_outgoing_ach, uow, clock)
    conn.execute("UPDATE holds SET state = 'released', finalized_at = ?", (NOW,))
    before = state(conn)
    refused = evidence(settle_outgoing_ach, uow, clock, ref="ev-s")
    assert isinstance(refused, Failure) and refused.error.code == "INVALID_TRANSITION"
    assert state(conn) == before
