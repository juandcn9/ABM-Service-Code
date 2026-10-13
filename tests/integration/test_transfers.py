"""Internal transfer: atomic equal debit and credit between two open accounts (FR-06, API-12)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest

from abm.application.caller import CallerContext
from abm.application.incoming_ach import create_incoming_ach, settle_incoming_ach
from abm.application.outgoing_ach import create_outgoing_ach
from abm.application.registration import register_account
from abm.application.transfers import internal_transfer
from abm.domain.results import Failure, Success
from abm.persistence.migrations import load_migrations
from abm.persistence.readiness import readiness_reasons, start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = load_migrations(ROOT / "migrations")
NOW = "2026-10-10T12:00:00Z"
REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")


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


def register(uow, clock, account: str, customer: str) -> None:
    body = {
        "instruction_id": f"ins-reg-{account}",
        "account_id": account,
        "customer_id": customer,
        "currency": "USD",
        "eligibility_reference": "elig-1",
    }
    assert isinstance(
        register_account(uow, clock, REGISTRAR, f"key-reg-{account}", body), Success
    )


def fund(uow, clock, account: str, cents: int) -> None:
    """Credit an account through the incoming ACH path, so the funds are real."""
    movement = f"mv-in-{account}"
    notice = {
        "instruction_id": f"ins-n-{account}",
        "movement_id": movement,
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": f"ext-{account}",
    }
    assert isinstance(
        create_incoming_ach(uow, clock, PAYER, f"kn-{account}", account, notice),
        Success,
    )
    settled = {
        "instruction_id": f"ins-s-{account}",
        "evidence_reference": f"ev-{account}",
    }
    assert isinstance(
        settle_incoming_ach(
            uow, clock, PAYER, f"ks-{account}", account, movement, settled
        ),
        Success,
    )


def transfer(
    uow,
    clock,
    source="acct-a",
    destination="acct-b",
    cents=300,
    movement="mv-t",
    key="kt",
    instruction="ins-t",
):
    body = {
        "instruction_id": instruction,
        "movement_id": movement,
        "source_account_id": source,
        "destination_account_id": destination,
        "amount_cents": cents,
        "currency": "USD",
    }
    return internal_transfer(uow, clock, PAYER, key, body)


def balances(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    rows = conn.execute(
        "SELECT account_id, current_balance_cents FROM accounts"
    ).fetchall()
    held = dict(
        conn.execute(
            "SELECT account_id, COALESCE(SUM(amount_cents), 0) FROM holds WHERE state = 'active' GROUP BY account_id"
        ).fetchall()
    )
    return {account: (current, held.get(account, 0)) for account, current in rows}


def counts(conn: sqlite3.Connection) -> tuple[int, ...]:
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("movements", "ledger_entries", "audit_trace", "holds")
    )


def ready_setup(uow, clock) -> None:
    register(uow, clock, "acct-a", "cust-a")
    register(uow, clock, "acct-b", "cust-b")
    fund(uow, clock, "acct-a", 1000)


def test_a_transfer_moves_equal_amounts_in_one_completed_movement(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    result = transfer(uow, clock)
    assert isinstance(result, Success)
    assert balances(conn) == {"acct-a": (700, 0), "acct-b": (300, 0)}
    rows = conn.execute(
        "SELECT account_id, effect_kind, direction, amount_cents FROM ledger_entries"
        " WHERE movement_id = 'mv-t' ORDER BY sequence"
    ).fetchall()
    assert rows == [
        ("acct-a", "transfer_source_debit", "debit", 300),
        ("acct-b", "transfer_destination_credit", "credit", 300),
    ]
    assert conn.execute(
        "SELECT movement_type, state, counterparty_account_id FROM movements WHERE movement_id = 'mv-t'"
    ).fetchone() == ("internal_transfer", "completed", "acct-b")
    assert conn.execute(
        "SELECT operation, movement_state FROM audit_trace WHERE operation = 'internal_transfer'"
    ).fetchone() == ("internal_transfer", "completed")


def test_insufficient_funds_is_refused_with_only_the_outcome_stored(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    before = counts(conn)
    result = transfer(uow, clock, cents=1500)
    assert isinstance(result, Failure) and result.error.code == "INSUFFICIENT_FUNDS"
    # the refusal is a deterministic rejection: its outcome is stored, nothing else changes
    assert counts(conn) == before
    assert conn.execute(
        "SELECT COUNT(*) FROM idempotency_outcomes WHERE http_status = 422"
    ).fetchone() == (1,)
    assert balances(conn) == {"acct-a": (1000, 0), "acct-b": (0, 0)}


def test_a_hold_on_the_source_reduces_what_can_be_transferred(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    hold = {
        "instruction_id": "ins-h",
        "movement_id": "mv-h",
        "amount_cents": 800,
        "currency": "USD",
        "external_reference": "ext-h",
        "destination_reference": "dest-h",
    }
    assert isinstance(
        create_outgoing_ach(uow, clock, PAYER, "kh", "acct-a", hold), Success
    )
    refused = transfer(uow, clock, cents=300)
    assert isinstance(refused, Failure) and refused.error.code == "INSUFFICIENT_FUNDS"


def test_a_restricted_source_or_a_closed_account_takes_no_transfer(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    conn.execute(
        "UPDATE accounts SET restriction = 'outgoing_blocked', restriction_decision_reference = 'dec-1' WHERE account_id = 'acct-a'"
    )
    blocked = transfer(uow, clock, movement="mv-r", key="kr", instruction="ins-r")
    assert isinstance(blocked, Failure) and blocked.error.code == "OUTGOING_BLOCKED"
    conn.execute(
        "UPDATE accounts SET restriction = 'none', restriction_decision_reference = NULL WHERE account_id = 'acct-a'"
    )
    conn.execute(
        "UPDATE accounts SET status = 'closed', closed_at = ? WHERE account_id = 'acct-b'",
        (NOW,),
    )
    closed = transfer(uow, clock, movement="mv-c", key="kc", instruction="ins-c")
    assert isinstance(closed, Failure) and closed.error.code == "ACCOUNT_CLOSED"


def test_an_unknown_account_is_not_found_and_the_same_account_is_refused(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    unknown = transfer(
        uow,
        clock,
        destination="acct-zz",
        movement="mv-u",
        key="ku",
        instruction="ins-u",
    )
    assert isinstance(unknown, Failure) and unknown.error.code == "ACCOUNT_NOT_FOUND"
    before = counts(conn)
    same = transfer(
        uow, clock, destination="acct-a", movement="mv-s", key="ks", instruction="ins-s"
    )
    assert isinstance(same, Failure) and same.error.code == "VALIDATION_ERROR"
    assert counts(conn) == before


def test_a_caller_without_the_role_is_refused_before_any_write(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    before = counts(conn)
    body = {
        "instruction_id": "ins-d",
        "movement_id": "mv-d",
        "source_account_id": "acct-a",
        "destination_account_id": "acct-b",
        "amount_cents": 1,
        "currency": "USD",
    }
    denied = internal_transfer(uow, clock, REGISTRAR, "kd", body)
    assert isinstance(denied, Failure) and denied.error.code == "FORBIDDEN_SCOPE"
    assert counts(conn) == before


def test_a_replay_returns_the_stored_outcome_and_a_changed_request_conflicts(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    first = transfer(uow, clock)
    before = counts(conn)
    again = transfer(uow, clock)
    assert (
        isinstance(again, Success)
        and again.replayed is True
        and again.value == first.value
    )
    assert counts(conn) == before
    changed = transfer(uow, clock, cents=301)
    assert isinstance(changed, Failure) and changed.error.code == "IDEMPOTENCY_CONFLICT"
    assert counts(conn) == before


def test_a_storage_fault_on_the_destination_rolls_everything_back(
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from abm.persistence import sqlite_store

    ready_setup(uow, clock)
    before = counts(conn)
    balances_before = balances(conn)
    real = sqlite_store.SqliteWriteTransaction.apply_balance

    def fault(self, account_id: str, delta: int) -> None:
        if account_id == "acct-b":
            raise sqlite3.OperationalError("injected fault")
        real(self, account_id, delta)

    monkeypatch.setattr(sqlite_store.SqliteWriteTransaction, "apply_balance", fault)
    result = transfer(uow, clock)
    # a driver error without a SQLite result code maps to INTERNAL_ERROR (database.to_failure)
    assert isinstance(result, Failure)
    assert result.error.code == "INTERNAL_ERROR"
    assert counts(conn) == before and balances(conn) == balances_before


def test_the_database_is_ready_after_transfers_and_a_restart(
    tmp_path: pathlib.Path,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    ready_setup(uow, clock)
    assert isinstance(transfer(uow, clock), Success)
    assert isinstance(
        transfer(
            uow, clock, cents=200, movement="mv-t2", key="kt2", instruction="ins-t2"
        ),
        Success,
    )
    conn.close()
    reopened = start_database(tmp_path / "abm.sqlite3", MIGRATIONS, NOW)
    assert reopened.ready and reopened.connection is not None
    assert readiness_reasons(reopened.connection, MIGRATIONS) == []
    assert balances(reopened.connection) == {"acct-a": (500, 0), "acct-b": (500, 0)}


def test_a_reused_movement_id_under_a_new_key_is_invalid_transition(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    assert isinstance(transfer(uow, clock), Success)
    before = counts(conn)
    again = transfer(uow, clock, key="kt-new", instruction="ins-t-new")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    # the refusal is a deterministic rejection: only its stored outcome is added (DEC-0025)
    assert counts(conn)[:3] == before[:3]
    assert balances(conn) == {"acct-a": (700, 0), "acct-b": (300, 0)}


def test_both_ledger_effects_appear_in_the_trace(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    assert isinstance(transfer(uow, clock), Success)
    traced = conn.execute(
        "SELECT account_id, ledger_entry_id FROM audit_trace WHERE operation = 'internal_transfer' ORDER BY sequence"
    ).fetchall()
    ledger = conn.execute(
        "SELECT account_id, entry_id FROM ledger_entries WHERE movement_id = 'mv-t' ORDER BY sequence"
    ).fetchall()
    assert traced == ledger


def test_a_closed_source_account_takes_no_transfer_and_nothing_is_written(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    ready_setup(uow, clock)
    conn.execute(
        "UPDATE accounts SET status = 'closed', closed_at = ? WHERE account_id = 'acct-a'",
        (NOW,),
    )
    before = (counts(conn), balances(conn))
    closed = transfer(uow, clock, movement="mv-cs", key="kcs", instruction="ins-cs")
    assert isinstance(closed, Failure) and closed.error.code == "ACCOUNT_CLOSED"
    assert (counts(conn), balances(conn)) == before
