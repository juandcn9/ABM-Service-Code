"""Incoming ACH: notice, settlement, and one full return (FR-02, FR-03, API-04..06, INV-10)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime
from typing import cast

import pytest

from abm.application.caller import CallerContext
from abm.application.idempotency import Response
from abm.application.incoming_ach import (
    create_incoming_ach,
    return_incoming_ach,
    settle_incoming_ach,
)
from abm.application.registration import register_account
from abm.domain.results import Failure, Result, Success
from abm.persistence.migrations import load_migrations
from abm.persistence.readiness import readiness_reasons, start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from abm.ports.storage import UnitOfWork
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
NOW = "2026-10-09T12:00:00Z"
REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
READER = CallerContext("reader-1", "account_reader", "corr-r", "acct-1")


@pytest.fixture
def conn(tmp_path: pathlib.Path) -> sqlite3.Connection:
    started = start_database(
        tmp_path / "abm.sqlite3", load_migrations(ROOT / "migrations"), NOW
    )
    assert started.connection is not None
    return started.connection


@pytest.fixture
def uow(conn: sqlite3.Connection) -> SqliteUnitOfWork:
    return SqliteUnitOfWork(conn)


@pytest.fixture
def clock() -> ControllableClock:
    return ControllableClock(datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC))


def registered(uow: SqliteUnitOfWork, clock: ControllableClock) -> None:
    body = {
        "instruction_id": "ins-reg",
        "account_id": "acct-1",
        "customer_id": "cust-1",
        "currency": "USD",
        "eligibility_reference": "elig-1",
    }
    assert isinstance(register_account(uow, clock, REGISTRAR, "key-reg", body), Success)


def notice(uow, clock, movement="mv-1", amount=500, key="key-n1", instruction="ins-n1"):
    body = {
        "instruction_id": instruction,
        "movement_id": movement,
        "amount_cents": amount,
        "currency": "USD",
        "external_reference": "ext-1",
    }
    return create_incoming_ach(uow, clock, PAYER, key, "acct-1", body)


def settle(
    uow, clock, movement="mv-1", evidence="ev-1", key="key-s1", instruction="ins-s1"
):
    body = {"instruction_id": instruction, "evidence_reference": evidence}
    return settle_incoming_ach(uow, clock, PAYER, key, "acct-1", movement, body)


def give_back(uow, clock, movement="mv-1", evidence="ev-r1", amount=500, key="key-r1"):
    body = {
        "instruction_id": f"ins-{key}",
        "evidence_reference": evidence,
        "amount_cents": amount,
        "currency": "USD",
    }
    return return_incoming_ach(uow, clock, PAYER, key, "acct-1", movement, body)


def data_of(result: Result[Response]) -> dict[str, object]:
    assert isinstance(result, Success), result
    return dict(result.value.data)


def counts(conn: sqlite3.Connection) -> tuple[int, ...]:
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "movements",
            "movement_evidence",
            "ledger_entries",
            "audit_trace",
            "idempotency_outcomes",
        )
    )


def balance(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-1'"
    ).fetchone()[0]


def test_notice_creates_a_pending_movement_with_no_balance_effect(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    before = counts(conn)
    data = data_of(notice(uow, clock))
    assert data["state"] == "pending" and data["movement_type"] == "incoming_ach"
    assert balance(conn) == 0
    assert conn.execute(
        "SELECT state FROM movements WHERE movement_id = 'mv-1'"
    ).fetchone() == ("pending",)
    assert conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone() == (0,)
    assert counts(conn)[0] == before[0] + 1 and counts(conn)[3] == before[3] + 1


def test_settlement_posts_one_credit_and_settles_the_movement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    data = data_of(settle(uow, clock))
    assert data["state"] == "settled"
    assert balance(conn) == 500
    rows = conn.execute(
        "SELECT effect_kind, direction, amount_cents FROM ledger_entries"
    ).fetchall()
    assert rows == [("incoming_settlement", "credit", 500)]
    assert conn.execute("SELECT evidence_kind FROM movement_evidence").fetchall() == [
        ("settlement",)
    ]


def test_return_posts_one_full_debit_and_returns_the_movement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    settle(uow, clock)
    data = data_of(give_back(uow, clock))
    assert data["state"] == "returned"
    assert balance(conn) == 0
    effects = conn.execute(
        "SELECT effect_kind, direction, amount_cents FROM ledger_entries ORDER BY sequence"
    ).fetchall()
    assert effects == [
        ("incoming_settlement", "credit", 500),
        ("incoming_return", "debit", 500),
    ]


def test_same_key_and_request_replays_without_a_second_effect(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    first = notice(uow, clock)
    before = counts(conn)
    second = notice(uow, clock)
    assert isinstance(second, Success) and second.replayed is True
    assert second.value == first.value
    assert counts(conn) == before


def test_same_key_with_a_changed_request_conflicts_and_changes_nothing(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    before = counts(conn)
    changed = notice(uow, clock, amount=999)
    assert isinstance(changed, Failure) and changed.error.code == "IDEMPOTENCY_CONFLICT"
    assert counts(conn) == before


def test_a_second_settlement_is_refused_and_has_no_effect(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    settle(uow, clock)
    before = counts(conn)
    again = settle(uow, clock, evidence="ev-2", key="key-s2", instruction="ins-s2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert balance(conn) == 500 and counts(conn)[2] == before[2]


def test_an_evidence_reference_cannot_be_reused_for_another_movement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock, movement="mv-1")
    notice(uow, clock, movement="mv-2", key="key-n2", instruction="ins-n2")
    settle(uow, clock, movement="mv-1", evidence="shared")
    before = counts(conn)
    reused = settle(
        uow,
        clock,
        movement="mv-2",
        evidence="shared",
        key="key-s3",
        instruction="ins-s3",
    )
    assert isinstance(reused, Failure) and reused.error.code == "INVALID_TRANSITION"
    # the refusal is a deterministic rejection: only its stored outcome is added (DEC-0011)
    assert counts(conn)[:4] == before[:4] and counts(conn)[4] == before[4] + 1


def test_a_return_before_settlement_is_refused(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    early = give_back(uow, clock)
    assert isinstance(early, Failure) and early.error.code == "INVALID_TRANSITION"
    assert balance(conn) == 0


def test_a_return_that_differs_from_the_settled_amount_is_refused(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    settle(uow, clock)
    wrong = give_back(uow, clock, amount=499)
    assert isinstance(wrong, Failure) and wrong.error.code == "AMOUNT_MISMATCH"
    assert balance(conn) == 500


def test_a_second_return_is_refused(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    settle(uow, clock)
    give_back(uow, clock)
    again = give_back(uow, clock, evidence="ev-r2", key="key-r2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert balance(conn) == 0


def test_an_unknown_movement_or_account_is_not_found(
    uow: SqliteUnitOfWork, clock: ControllableClock
) -> None:
    registered(uow, clock)
    unknown_movement = settle(uow, clock, movement="nope")
    assert (
        isinstance(unknown_movement, Failure)
        and unknown_movement.error.code == "MOVEMENT_NOT_FOUND"
    )
    unknown_account = settle_incoming_ach(
        uow,
        clock,
        PAYER,
        "key-x",
        "acct-9",
        "mv-1",
        {"instruction_id": "ins-x", "evidence_reference": "ev-x"},
    )
    assert (
        isinstance(unknown_account, Failure)
        and unknown_account.error.code == "ACCOUNT_NOT_FOUND"
    )


def test_a_closed_account_takes_no_new_incoming_movement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    conn.execute(
        "UPDATE accounts SET status = 'closed', closed_at = ? WHERE account_id = 'acct-1'",
        (NOW,),
    )
    refused = notice(uow, clock)
    assert isinstance(refused, Failure) and refused.error.code == "ACCOUNT_CLOSED"
    assert counts(conn)[0] == 0


class _Untouchable:
    """A unit of work that fails the test if authorization lets a request reach storage."""

    def write(self) -> None:
        raise AssertionError("storage was reached")

    def read(self) -> None:
        raise AssertionError("storage was reached")


def test_a_caller_without_the_role_is_refused_before_any_storage_access(
    clock: ControllableClock,
) -> None:
    denied = create_incoming_ach(
        cast(UnitOfWork, _Untouchable()),
        clock,
        REGISTRAR,
        "key-d",
        "acct-1",
        {
            "instruction_id": "ins-d",
            "movement_id": "mv-d",
            "amount_cents": 5,
            "currency": "USD",
            "external_reference": "e",
        },
    )
    assert isinstance(denied, Failure) and denied.error.code == "FORBIDDEN_SCOPE"


@pytest.mark.parametrize(
    "amount", [0, -1, 9_007_199_254_740_992, 1.5, "500", True, None]
)
def test_invalid_amounts_are_refused_with_nothing_stored(
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
    amount: object,
) -> None:
    registered(uow, clock)
    before = counts(conn)
    result = notice(uow, clock, amount=amount)  # type: ignore[arg-type]
    assert isinstance(result, Failure) and result.error.code == "VALIDATION_ERROR"
    assert counts(conn) == before


def test_a_storage_fault_mid_settlement_rolls_everything_back(
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from abm.persistence import sqlite_store

    registered(uow, clock)
    notice(uow, clock)
    before = counts(conn)
    balance_before = balance(conn)

    def fault(self: object, account_id: str, delta: int) -> None:
        raise sqlite3.OperationalError("injected fault")

    monkeypatch.setattr(sqlite_store.SqliteWriteTransaction, "apply_balance", fault)
    result = settle(uow, clock)
    assert isinstance(result, Failure)
    assert counts(conn) == before and balance(conn) == balance_before
    assert conn.execute(
        "SELECT state FROM movements WHERE movement_id = 'mv-1'"
    ).fetchone() == ("pending",)


def test_the_database_is_ready_after_a_full_lifecycle_and_a_restart(
    tmp_path: pathlib.Path,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    settle(uow, clock)
    give_back(uow, clock)
    conn.close()
    reopened = start_database(
        tmp_path / "abm.sqlite3", load_migrations(ROOT / "migrations"), NOW
    )
    assert reopened.ready and reopened.connection is not None
    assert (
        readiness_reasons(reopened.connection, load_migrations(ROOT / "migrations"))
        == []
    )
    outcome = reopened.connection.execute(
        "SELECT outcome FROM audit_trace WHERE operation = 'return_incoming_ach'"
    ).fetchone()
    assert outcome == ("accepted",)


def test_settlement_records_its_trace_entry_with_the_credit_and_evidence(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    settle(uow, clock)
    row = conn.execute(
        "SELECT operation, movement_state, evidence_reference, ledger_entry_id, outcome"
        " FROM audit_trace WHERE operation = 'settle_incoming_ach'"
    ).fetchone()
    assert row is not None
    assert row[1:3] == ("settled", "ev-1") and row[4] == "accepted"
    assert conn.execute("SELECT entry_id FROM ledger_entries").fetchone() == (row[3],)


@pytest.mark.parametrize("operation", ["settle", "return"])
def test_a_closed_account_refuses_settlement_but_accepts_its_return(
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
    operation: str,
) -> None:
    # INV-16 permits return as late evidence after closure; settlement is not on that list
    registered(uow, clock)
    notice(uow, clock)
    if operation == "return":
        settle(uow, clock)
    conn.execute(
        "UPDATE accounts SET status = 'closed', closed_at = ? WHERE account_id = 'acct-1'",
        (NOW,),
    )
    before = counts(conn)
    if operation == "settle":
        result = settle(uow, clock, evidence="ev-c", key="key-c")
        assert isinstance(result, Failure) and result.error.code == "ACCOUNT_CLOSED"
        assert counts(conn)[:4] == before[:4]
    else:
        result = give_back(uow, clock, evidence="ev-c", key="key-c")
        assert isinstance(result, Success) and data_of(result)["state"] == "returned"
        assert balance(conn) == 0


def test_a_duplicate_movement_id_under_a_new_key_is_invalid_transition(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
    notice(uow, clock)
    before = counts(conn)
    again = notice(uow, clock, key="key-n-new", instruction="ins-n-new")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert counts(conn)[:4] == before[:4] and counts(conn)[4] == before[4] + 1


def test_another_accounts_movement_is_not_found_for_settlement_or_return(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    registered(uow, clock)
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
    assert isinstance(notice(uow, clock, movement="mv-1"), Success)
    assert isinstance(
        notice(uow, clock, movement="mv-2", key="key-n2", instruction="ins-n2"),
        Success,
    )
    assert isinstance(settle(uow, clock, movement="mv-1"), Success)

    def effects() -> tuple[object, ...]:
        return (
            conn.execute("SELECT COUNT(*) FROM movements").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0],
            conn.execute(
                "SELECT account_id, current_balance_cents FROM accounts ORDER BY account_id"
            ).fetchall(),
        )

    before = effects()
    wrong_settle = settle_incoming_ach(
        uow,
        clock,
        PAYER,
        "key-x1",
        "acct-2",
        "mv-2",
        {"instruction_id": "ins-x1", "evidence_reference": "ev-x1"},
    )
    assert isinstance(wrong_settle, Failure)
    assert wrong_settle.error.code == "MOVEMENT_NOT_FOUND"
    wrong_return = return_incoming_ach(
        uow,
        clock,
        PAYER,
        "key-x2",
        "acct-2",
        "mv-1",
        {
            "instruction_id": "ins-x2",
            "evidence_reference": "ev-x2",
            "amount_cents": 500,
            "currency": "USD",
        },
    )
    assert isinstance(wrong_return, Failure)
    assert wrong_return.error.code == "MOVEMENT_NOT_FOUND"
    assert effects() == before
