"""Card: authorization with hold, clearing, reversal, expiry, late clearing, and one full refund (FR-07, FR-08)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest

from abm.application.caller import CallerContext
from abm.application.cards import (
    authorize_card,
    clear_card,
    expire_card,
    refund_card,
    reverse_card,
)
from abm.application.incoming_ach import create_incoming_ach, settle_incoming_ach
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
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")


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


def data_of(result: Result) -> dict[str, object]:
    assert isinstance(result, Success), result
    return dict(result.value.data)


def funded(uow, clock, cents: int = 1000) -> None:
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
        create_incoming_ach(uow, clock, PAYER, "kin-n", "acct-1", notice), Success
    )
    settled = {"instruction_id": "ins-in-s", "evidence_reference": "ev-in"}
    assert isinstance(
        settle_incoming_ach(uow, clock, PAYER, "kin-s", "acct-1", "mv-in", settled),
        Success,
    )


def authorize(uow, clock, movement="mv-card", cents=400, key="ka", instruction="ia"):
    body = {
        "instruction_id": instruction,
        "movement_id": movement,
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": f"ext-{movement}",
        "merchant_reference": "merchant-1",
    }
    return authorize_card(uow, clock, CARD, key, "acct-1", body)


def step(
    fn,
    uow,
    clock,
    movement="mv-card",
    cents=400,
    ref="ev-1",
    key=None,
    instruction=None,
):
    body = {
        "instruction_id": instruction or f"i-{ref}",
        "evidence_reference": ref,
        "amount_cents": cents,
        "currency": "USD",
    }
    return fn(uow, clock, CARD, key or f"k-{ref}", "acct-1", movement, body)


def simple(fn, uow, clock, movement="mv-card", ref="ev-1", key=None):
    body = {"instruction_id": f"i-{ref}", "evidence_reference": ref}
    return fn(uow, clock, CARD, key or f"k-{ref}", "acct-1", movement, body)


def balances(conn: sqlite3.Connection) -> tuple[int, int]:
    current = conn.execute("SELECT current_balance_cents FROM accounts").fetchone()[0]
    held = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM holds WHERE state = 'active'"
    ).fetchone()[0]
    return current, held


def state_of(conn: sqlite3.Connection, movement: str = "mv-card") -> str:
    return conn.execute(
        "SELECT state FROM movements WHERE movement_id = ?", (movement,)
    ).fetchone()[0]


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


def test_authorization_holds_the_funds_and_stores_the_merchant_reference(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    data = data_of(authorize(uow, clock))
    assert data["state"] == "authorized_with_hold" and data["movement_type"] == "card"
    assert balances(conn) == (1000, 400)
    assert conn.execute(
        "SELECT merchant_reference FROM movements WHERE movement_id = 'mv-card'"
    ).fetchone() == ("merchant-1",)
    assert conn.execute(
        "SELECT COUNT(*) FROM ledger_entries WHERE movement_id = 'mv-card'"
    ).fetchone() == (0,)


def test_authorization_is_refused_without_funds_or_on_a_blocked_account(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    short = authorize(
        uow, clock, cents=1500, key="kb", instruction="ib", movement="mv-x"
    )
    assert isinstance(short, Failure) and short.error.code == "INSUFFICIENT_FUNDS"
    conn.execute(
        "UPDATE accounts SET restriction = 'outgoing_blocked', restriction_decision_reference = 'dec-1'"
    )
    blocked = authorize(uow, clock, movement="mv-y", key="kc", instruction="ic")
    assert isinstance(blocked, Failure) and blocked.error.code == "OUTGOING_BLOCKED"


def test_a_reused_movement_id_is_invalid_transition_and_declared(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    assert isinstance(authorize(uow, clock), Success)
    before = counts(conn)
    again = authorize(uow, clock, key="ka2", instruction="ia2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert counts(conn)[:3] == before[:3]


def test_clearing_at_the_authorized_amount_releases_the_hold_and_posts_one_debit(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    assert data_of(step(clear_card, uow, clock, cents=400))["state"] == "cleared"
    assert balances(conn) == (600, 0)
    assert conn.execute(
        "SELECT effect_kind, direction, amount_cents FROM ledger_entries WHERE effect_kind = 'card_clearing'"
    ).fetchall() == [("card_clearing", "debit", 400)]
    assert conn.execute(
        "SELECT state FROM holds WHERE movement_id = 'mv-card'"
    ).fetchone() == ("posted",)


def test_clearing_may_differ_from_the_authorized_amount_and_create_an_allowed_negative_balance(
    tmp_path: pathlib.Path,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    assert data_of(step(clear_card, uow, clock, cents=1500))["state"] == "cleared"
    assert balances(conn) == (-500, 0)
    conn.close()
    reopened = start_database(tmp_path / "abm.sqlite3", MIGRATIONS, NOW)
    assert reopened.ready and reopened.connection is not None
    assert readiness_reasons(reopened.connection, MIGRATIONS) == []


def test_reversal_releases_the_hold_without_posting(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    assert data_of(simple(reverse_card, uow, clock, ref="ev-r"))["state"] == "reversed"
    assert balances(conn) == (1000, 0)
    assert conn.execute(
        "SELECT COUNT(*) FROM ledger_entries WHERE effect_kind = 'card_clearing'"
    ).fetchone() == (0,)
    again = simple(reverse_card, uow, clock, ref="ev-r2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"


def test_expiry_releases_the_hold_without_posting(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    assert data_of(simple(expire_card, uow, clock, ref="ev-e"))["state"] == "expired"
    assert balances(conn) == (1000, 0)


def test_a_late_clearing_after_reversal_posts_one_debit_without_a_hold(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    simple(reverse_card, uow, clock, ref="ev-r")
    data = data_of(step(clear_card, uow, clock, cents=400))
    assert data["state"] == "late_cleared"
    assert balances(conn) == (600, 0)
    # the response reports the same balances as the database: no hold is released or created
    account = data["accounts"][0]  # type: ignore[index]
    assert account["current_balance_cents"] == 600
    assert account["held_balance_cents"] == 0
    assert account["available_balance_cents"] == 600


def test_a_late_clearing_is_accepted_after_closure_and_never_reopens_the_account(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    simple(expire_card, uow, clock, ref="ev-e")
    conn.execute("UPDATE accounts SET status = 'closed', closed_at = ?", (NOW,))
    assert data_of(step(clear_card, uow, clock, cents=400))["state"] == "late_cleared"
    assert conn.execute("SELECT status FROM accounts").fetchone() == ("closed",)


def test_a_cleared_movement_cannot_be_cleared_again_or_reversed(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    step(clear_card, uow, clock, cents=400)
    again = step(clear_card, uow, clock, cents=400, ref="ev-2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    reversed_now = simple(reverse_card, uow, clock, ref="ev-3")
    assert (
        isinstance(reversed_now, Failure)
        and reversed_now.error.code == "INVALID_TRANSITION"
    )


def test_a_full_refund_after_clearing_posts_one_credit(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    step(clear_card, uow, clock, cents=400)
    assert (
        data_of(step(refund_card, uow, clock, cents=400, ref="ev-f"))["state"]
        == "refunded"
    )
    assert balances(conn) == (1000, 0)
    assert conn.execute(
        "SELECT direction, amount_cents FROM ledger_entries WHERE effect_kind = 'card_refund'"
    ).fetchall() == [("credit", 400)]


def test_a_partial_refund_or_a_refund_before_clearing_is_refused(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    early = step(refund_card, uow, clock, cents=400, ref="ev-early")
    assert isinstance(early, Failure) and early.error.code == "INVALID_TRANSITION"
    step(clear_card, uow, clock, cents=400)
    partial = step(refund_card, uow, clock, cents=300, ref="ev-p")
    assert isinstance(partial, Failure) and partial.error.code == "AMOUNT_MISMATCH"
    assert balances(conn) == (600, 0)


def test_a_caller_without_the_role_is_refused_before_any_write(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    before = counts(conn)
    body = {
        "instruction_id": "ix",
        "movement_id": "mv-d",
        "amount_cents": 5,
        "currency": "USD",
        "external_reference": "e",
        "merchant_reference": "m",
    }
    denied = authorize_card(uow, clock, PAYER, "kd", "acct-1", body)
    assert isinstance(denied, Failure) and denied.error.code == "FORBIDDEN_SCOPE"
    assert counts(conn) == before


def test_a_replay_returns_the_stored_outcome(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    funded(uow, clock)
    first = authorize(uow, clock)
    before = counts(conn)
    again = authorize(uow, clock)
    assert (
        isinstance(again, Success)
        and again.replayed is True
        and again.value == first.value
    )
    assert counts(conn) == before


def test_a_storage_fault_during_clearing_rolls_everything_back(
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from abm.persistence import sqlite_store

    funded(uow, clock)
    authorize(uow, clock)
    before = counts(conn)
    balances_before = balances(conn)

    def fault(self, account_id: str, delta: int) -> None:
        raise sqlite3.OperationalError("injected fault")

    monkeypatch.setattr(sqlite_store.SqliteWriteTransaction, "apply_balance", fault)
    result = step(clear_card, uow, clock, cents=400)
    assert isinstance(result, Failure)
    assert counts(conn) == before and balances(conn) == balances_before
    assert state_of(conn) == "authorized_with_hold"


def test_a_card_operation_on_another_accounts_movement_is_not_found(
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    funded(uow, clock)
    authorize(uow, clock)
    other = {
        "instruction_id": "ins-reg-2",
        "account_id": "acct-2",
        "customer_id": "cust-2",
        "currency": "USD",
        "eligibility_reference": "elig-2",
    }
    assert isinstance(
        register_account(uow, clock, REGISTRAR, "key-reg-2", other), Success
    )
    before = (balances(conn), counts(conn))
    with_amount = {
        "instruction_id": "i-x",
        "evidence_reference": "ev-x",
        "amount_cents": 400,
        "currency": "USD",
    }
    without_amount = {"instruction_id": "i-y", "evidence_reference": "ev-y"}
    attempts = [
        (clear_card, with_amount),
        (reverse_card, without_amount),
        (expire_card, without_amount),
        (refund_card, with_amount),
    ]
    for fn, body in attempts:
        result = fn(uow, clock, CARD, f"k-{fn.__name__}", "acct-2", "mv-card", body)
        assert (
            isinstance(result, Failure) and result.error.code == "MOVEMENT_NOT_FOUND"
        ), fn.__name__
    assert (balances(conn), counts(conn)) == before
    assert state_of(conn) == "authorized_with_hold"
