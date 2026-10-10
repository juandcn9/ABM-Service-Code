"""Account, history, and trace reads (TEST-11, TEST-12; FR-11, FR-12, FR-13; BT-04, BT-05; INV-05)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest

from abm.application.caller import CallerContext
from abm.application.idempotency import Response
from abm.application.reads import get_account, get_history, get_trace
from abm.application.registration import register_account
from abm.domain.results import Failure, Result, Success
from abm.persistence.database import open_database
from abm.persistence.migrations import load_migrations
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
NOW = "2026-10-09T12:00:00Z"
READER = CallerContext("reader-1", "account_reader", "corr-r", "acct-1")
RECON = CallerContext("recon-1", "reconciliation_reader", "corr-t")


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


def register(
    uow: SqliteUnitOfWork, account: str = "acct-1", customer: str = "cust-1"
) -> None:
    clock = ControllableClock(datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC))
    body = {
        "instruction_id": f"ins-{account}",
        "account_id": account,
        "customer_id": customer,
        "currency": "USD",
        "eligibility_reference": "elig-1",
    }
    result = register_account(
        uow,
        clock,
        CallerContext("registrar-1", "account_registrar", "corr-1"),
        f"key-{account}",
        body,
    )
    assert isinstance(result, Success)


def post(
    conn: sqlite3.Connection, account: str, n: int, direction: str, cents: int
) -> None:
    """Record one posted entry the way a later money task will: movement, entry, projection, trace."""
    kind, state = (
        ("incoming_settlement", "settled")
        if direction == "credit"
        else ("incoming_return", "returned")
    )
    movement = f"{account}-m{n}"
    conn.execute(
        "INSERT INTO movements (movement_id, account_id, movement_type, state, amount_cents, currency,"
        " created_at, updated_at) VALUES (?, ?, 'incoming_ach', ?, ?, 'USD', ?, ?)",
        (movement, account, state, cents, NOW, NOW),
    )
    entry = f"{account}-l{n}"
    conn.execute(
        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind, direction,"
        " amount_cents, authorized_caller_id, authorized_role, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'pay-1', 'payment_orchestrator', ?)",
        (entry, account, movement, kind, direction, cents, NOW),
    )
    delta = cents if direction == "credit" else -cents
    conn.execute(
        "UPDATE accounts SET current_balance_cents = current_balance_cents + ? WHERE account_id = ?",
        (delta, account),
    )
    conn.execute(
        "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind, occurred_at)"
        " VALUES (?, ?, ?, ?)",
        (
            f"ev-{account}-{n}",
            movement,
            "settlement" if direction == "credit" else "return",
            NOW,
        ),
    )
    conn.execute(
        "INSERT INTO audit_trace (account_id, instruction_id, movement_id, ledger_entry_id,"
        " evidence_reference, movement_state, operation, outcome, caller_id, caller_role,"
        " correlation_id, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', 'pay-1',"
        " 'payment_orchestrator', 'corr-p', ?)",
        (
            account,
            f"ins-p{account}{n}",
            movement,
            entry,
            f"ev-{account}-{n}",
            state,
            kind,
            NOW,
        ),
    )


def hold(conn: sqlite3.Connection, account: str, n: int, cents: int) -> None:
    movement = f"{account}-h{n}"
    conn.execute(
        "INSERT INTO movements (movement_id, account_id, movement_type, state, amount_cents, currency,"
        " created_at, updated_at) VALUES (?, ?, 'outgoing_ach', 'accepted_with_hold', ?, 'USD', ?, ?)",
        (movement, account, cents, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO holds (hold_id, movement_id, account_id, amount_cents, state, created_at)"
        " VALUES (?, ?, ?, ?, 'active', ?)",
        (f"{account}-hold{n}", movement, account, cents, NOW),
    )


def ok(result: Result[Response]) -> dict[str, object]:
    assert isinstance(result, Success), result
    assert result.value.status == 200 and result.replayed is False
    return dict(result.value.data)


def snapshot(conn: sqlite3.Connection) -> list[str]:
    return list(conn.iterdump())


# TEST-11: account read


def test_new_account_reads_as_zero_state(uow: SqliteUnitOfWork) -> None:
    register(uow)
    assert ok(get_account(uow, READER, "acct-1")) == {
        "account_id": "acct-1",
        "currency": "USD",
        "status": "open",
        "restriction": "none",
        "balances": {
            "account_id": "acct-1",
            "current_balance_cents": 0,
            "held_balance_cents": 0,
            "available_balance_cents": 0,
        },
        "active_holds": [],
    }


def test_balances_are_posted_held_and_derived_available(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    post(conn, "acct-1", 1, "credit", 1000)
    post(conn, "acct-1", 2, "debit", 300)
    hold(conn, "acct-1", 1, 250)
    hold(conn, "acct-1", 2, 100)
    data = ok(get_account(uow, READER, "acct-1"))
    assert data["balances"] == {
        "account_id": "acct-1",
        "current_balance_cents": 700,
        "held_balance_cents": 350,
        "available_balance_cents": 350,
    }
    holds = data["active_holds"]
    assert isinstance(holds, list) and [h["amount_cents"] for h in holds] == [250, 100]
    assert all(h["state"] == "active" for h in holds)


def test_released_holds_are_not_listed_or_counted(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    post(conn, "acct-1", 1, "credit", 500)
    hold(conn, "acct-1", 1, 200)
    conn.execute("UPDATE holds SET state = 'released', finalized_at = ?", (NOW,))
    data = ok(get_account(uow, READER, "acct-1"))
    assert data["active_holds"] == []
    balances = data["balances"]
    assert isinstance(balances, dict) and balances["available_balance_cents"] == 500


def test_available_balance_may_be_negative_when_the_ledger_allows_it(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    post(conn, "acct-1", 1, "debit", 400)
    balances = ok(get_account(uow, READER, "acct-1"))["balances"]
    assert isinstance(balances, dict)
    assert (
        balances["current_balance_cents"] == -400
        and balances["available_balance_cents"] == -400
    )


def test_reader_is_limited_to_its_exact_account_and_unknown_is_not_found(
    uow: SqliteUnitOfWork,
) -> None:
    register(uow)
    register(uow, "acct-2", "cust-2")
    wrong = get_account(uow, READER, "acct-2")
    assert isinstance(wrong, Failure) and wrong.error.code == "FORBIDDEN_SCOPE"
    other_role = get_account(
        uow, CallerContext("p", "payment_orchestrator", "c", "acct-1"), "acct-1"
    )
    assert (
        isinstance(other_role, Failure) and other_role.error.code == "FORBIDDEN_SCOPE"
    )
    scoped_unknown = CallerContext("r", "account_reader", "c", "ghost")
    missing = get_account(uow, scoped_unknown, "ghost")
    assert isinstance(missing, Failure) and missing.error.code == "ACCOUNT_NOT_FOUND"
    bad_id = get_account(uow, READER, "bad id")
    assert isinstance(bad_id, Failure) and bad_id.error.code == "VALIDATION_ERROR"


def test_denied_reads_never_touch_storage() -> None:
    class Forbidden:
        def read(self) -> object:
            raise AssertionError("storage must not be touched before authorization")

    denied = CallerContext("r", "account_reader", "c", "acct-9")
    result = get_account(Forbidden(), denied, "acct-1")  # type: ignore[arg-type]
    assert isinstance(result, Failure) and result.error.code == "FORBIDDEN_SCOPE"
    result = get_trace(Forbidden(), READER)  # type: ignore[arg-type]
    assert isinstance(result, Failure) and result.error.code == "FORBIDDEN_SCOPE"


# TEST-12: history


def test_history_is_stable_ordered_and_pages_without_gaps_or_duplicates(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    register(uow, "acct-2", "cust-2")
    for n in range(1, 8):
        post(conn, "acct-1", n, "credit", 100 * n)
        post(
            conn, "acct-2", n, "credit", 7
        )  # another account's entries must never appear
    seen: list[int] = []
    cursor = 0
    pages = 0
    while True:
        data = ok(get_history(uow, READER, "acct-1", cursor, 3))
        items = data["items"]
        assert isinstance(items, list) and len(items) <= 3
        seen.extend(item["sequence"] for item in items)
        pages += 1
        cursor_next = data["next_after_sequence"]
        if cursor_next is None:
            break
        assert isinstance(cursor_next, int) and cursor_next == items[-1]["sequence"]
        cursor = cursor_next
    assert pages == 3 and len(seen) == 7 and seen == sorted(set(seen))
    amounts = [
        item["amount_cents"]
        for item in ok(get_history(uow, READER, "acct-1", 0, 200))["items"]  # type: ignore[attr-defined]
    ]
    assert amounts == [100 * n for n in range(1, 8)]


def test_history_entry_shape_and_empty_account(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    empty = ok(get_history(uow, READER, "acct-1"))
    assert empty == {"account_id": "acct-1", "items": [], "next_after_sequence": None}
    post(conn, "acct-1", 1, "credit", 500)
    entry = ok(get_history(uow, READER, "acct-1"))["items"][0]  # type: ignore[index]
    assert entry == {
        "sequence": 1,
        "entry_id": "acct-1-l1",
        "movement_id": "acct-1-m1",
        "effect_kind": "incoming_settlement",
        "direction": "credit",
        "amount_cents": 500,
        "currency": "USD",
        "created_at": NOW,
    }


def test_history_exact_page_boundary_has_no_phantom_next_page(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    for n in range(1, 4):
        post(conn, "acct-1", n, "credit", 10)
    assert ok(get_history(uow, READER, "acct-1", 0, 3))["next_after_sequence"] is None
    assert ok(get_history(uow, READER, "acct-1", 0, 2))["next_after_sequence"] == 2
    assert ok(get_history(uow, READER, "acct-1", 99, 3))["items"] == []


@pytest.mark.parametrize(
    ("after", "limit"),
    [
        (-1, 10),
        (0, 0),
        (0, 201),
        (0, -5),
        ("0", 10),
        (0, "10"),
        (1.5, 10),
        (0, 2.0),
        (True, 10),
        (0, True),
        (None, 10),
    ],
)
def test_history_query_bounds_are_enforced(
    uow: SqliteUnitOfWork, after: object, limit: object
) -> None:
    register(uow)
    result = get_history(uow, READER, "acct-1", after, limit)
    assert isinstance(result, Failure) and result.error.code == "VALIDATION_ERROR"


def test_history_for_unknown_account_is_not_found_and_other_scope_denied(
    uow: SqliteUnitOfWork,
) -> None:
    ghost = CallerContext("r", "account_reader", "c", "ghost")
    missing = get_history(uow, ghost, "ghost")
    assert isinstance(missing, Failure) and missing.error.code == "ACCOUNT_NOT_FOUND"
    denied = get_history(uow, READER, "acct-2")
    assert isinstance(denied, Failure) and denied.error.code == "FORBIDDEN_SCOPE"


# TEST-12: reconciliation trace


def test_trace_first_page_captures_the_cutoff_and_later_pages_honor_it(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    for n in range(1, 6):
        post(
            conn, "acct-1", n, "credit", 10
        )  # trace sequences 2..6 (1 is the registration)
    first = ok(get_trace(uow, RECON, 0, 4))
    assert first["cutoff_sequence"] == 6 and first["next_after_sequence"] == 4
    # records committed after the first page must stay invisible to this walk
    post(conn, "acct-1", 6, "credit", 10)
    post(conn, "acct-1", 7, "credit", 10)
    second = ok(get_trace(uow, RECON, 4, 4, first["cutoff_sequence"]))
    items = second["items"]
    assert isinstance(items, list) and [i["sequence"] for i in items] == [5, 6]
    assert second["cutoff_sequence"] == 6 and second["next_after_sequence"] is None
    fresh = ok(
        get_trace(uow, RECON, 0, 100)
    )  # a new walk sees everything committed since
    assert fresh["cutoff_sequence"] == 8


def test_full_walk_returns_every_record_once_in_order(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    for n in range(1, 10):
        post(conn, "acct-1", n, "credit", 10)
    page = ok(get_trace(uow, RECON, 0, 3))
    cutoff = page["cutoff_sequence"]
    sequences: list[int] = [i["sequence"] for i in page["items"]]  # type: ignore[attr-defined]
    while page["next_after_sequence"] is not None:
        page = ok(get_trace(uow, RECON, page["next_after_sequence"], 3, cutoff))
        sequences.extend(i["sequence"] for i in page["items"])  # type: ignore[attr-defined]
    assert sequences == list(range(1, 11))


def test_trace_records_expose_immutable_matching_fields(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    post(conn, "acct-1", 1, "credit", 500)
    items = ok(get_trace(uow, RECON))["items"]
    assert isinstance(items, list)
    registration, money = items
    assert registration["operation"] == "register_account"
    assert (
        registration["ledger_entry_id"] is None and registration["amount_cents"] is None
    )
    assert registration["currency"] is None and registration["effect_kind"] is None
    assert money == {
        "sequence": 2,
        "account_id": "acct-1",
        "instruction_id": "ins-pacct-11",
        "movement_id": "acct-1-m1",
        "operation": "incoming_settlement",
        "caller_id": "pay-1",
        "caller_role": "payment_orchestrator",
        "correlation_id": "corr-p",
        "occurred_at": NOW,
        "ledger_entry_id": "acct-1-l1",
        "movement_state": "settled",
        "effect_kind": "incoming_settlement",
        "direction": "credit",
        "amount_cents": 500,
        "currency": "USD",
        "evidence_reference": "ev-acct-1-1",
        "external_reference": None,
    }


def test_trace_empty_database_has_cutoff_zero(uow: SqliteUnitOfWork) -> None:
    assert ok(get_trace(uow, RECON)) == {
        "cutoff_sequence": 0,
        "items": [],
        "next_after_sequence": None,
    }
    again = ok(get_trace(uow, RECON, 0, 100, 0))
    assert again["cutoff_sequence"] == 0


def test_trace_cutoff_beyond_the_committed_end_is_refused(
    uow: SqliteUnitOfWork,
) -> None:
    register(uow)
    result = get_trace(uow, RECON, 0, 100, 999)
    assert isinstance(result, Failure) and result.error.code == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("after", "limit", "cutoff"),
    [
        (-1, 10, None),
        (0, 0, None),
        (0, 1001, None),
        (0, 10, -1),
        ("0", 10, None),
        (0, 10, "5"),
        (0, 10, 1.0),
        (True, 10, None),
        (0, 10, True),
    ],
)
def test_trace_query_bounds_are_enforced(
    uow: SqliteUnitOfWork, after: object, limit: object, cutoff: object
) -> None:
    register(uow)
    result = get_trace(uow, RECON, after, limit, cutoff)
    assert isinstance(result, Failure) and result.error.code == "VALIDATION_ERROR"


def test_only_the_reconciliation_reader_may_read_the_trace(
    uow: SqliteUnitOfWork,
) -> None:
    register(uow)
    for role in (
        "account_reader",
        "payment_orchestrator",
        "account_registrar",
        "nobody",
    ):
        result = get_trace(uow, CallerContext("c-1", role, "corr", "acct-1"))
        assert isinstance(result, Failure) and result.error.code == "FORBIDDEN_SCOPE", (
            role
        )


def test_reads_change_nothing_and_store_no_outcome(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    register(uow)
    post(conn, "acct-1", 1, "credit", 500)
    before = snapshot(conn)
    get_account(uow, READER, "acct-1")
    get_history(uow, READER, "acct-1")
    get_trace(uow, RECON)
    assert snapshot(conn) == before
    assert not conn.in_transaction


@pytest.mark.parametrize("value", [2**63, 2**64, -1])
def test_oversized_or_negative_cursors_are_validation_errors(
    uow: SqliteUnitOfWork, value: int
) -> None:
    # values beyond the SQLite INTEGER range must be refused before any query binds them
    register(uow, "acct-1")  # an existing account, so the query itself is reached
    history = get_history(uow, READER, "acct-1", after_sequence=value)
    trace = get_trace(uow, RECON, after_sequence=value)
    assert isinstance(history, Failure) and history.error.code == "VALIDATION_ERROR"
    assert isinstance(trace, Failure) and trace.error.code == "VALIDATION_ERROR"


def test_a_read_transaction_keeps_one_snapshot_while_another_connection_commits(
    tmp_path: pathlib.Path, conn: sqlite3.Connection, uow: SqliteUnitOfWork
) -> None:
    # BT-04 and BT-05: balances, history and trace seen inside one read come from one committed state
    register(uow, "acct-1")
    other = open_database(tmp_path / "abm.sqlite3")
    with uow.read() as tx:
        before_history = tx.history_page("acct-1", 0, 100)
        before_cutoff = tx.trace_cutoff()
        register(
            SqliteUnitOfWork(other), "acct-2", "cust-2"
        )  # committed by another connection mid-read
        assert tx.history_page("acct-1", 0, 100) == before_history
        assert tx.trace_cutoff() == before_cutoff
    with uow.read() as fresh:
        assert fresh.trace_cutoff() > before_cutoff  # a fresh read sees the new commit
    other.close()
