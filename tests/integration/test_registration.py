"""Registration and transactional idempotency (TEST-01, TEST-15, TEST-16; FR-01, BT-09, INV-02, INV-03, INV-06, INV-17)."""

from __future__ import annotations

import pathlib
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from abm.application.caller import CallerContext
from abm.application.idempotency import Response, run_idempotent, scope_key
from abm.application.registration import register_account
from abm.domain.results import Failure, Success, failure
from abm.persistence.database import open_database, write_transaction
from abm.persistence.migrations import apply_migrations, load_migrations
from abm.persistence.sqlite_store import SqliteUnitOfWork
from abm.ports.storage import NewAccount, UnitOfWork, WriteTransaction
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
BODY: dict[str, object] = {
    "instruction_id": "ins-1",
    "account_id": "acct-1",
    "customer_id": "cust-1",
    "currency": "USD",
    "eligibility_reference": "elig-1",
}
TABLES = (
    "accounts",
    "retention_metadata",
    "audit_trace",
    "idempotency_outcomes",
    "movements",
    "holds",
    "ledger_entries",
    "movement_evidence",
)


@pytest.fixture
def db_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "abm.sqlite3"
    conn = open_database(path)
    apply_migrations(conn, load_migrations(ROOT / "migrations"), "2026-10-09T11:00:00Z")
    conn.close()
    return path


@pytest.fixture
def conn(db_path: pathlib.Path) -> sqlite3.Connection:
    return open_database(db_path)


@pytest.fixture
def uow(conn: sqlite3.Connection) -> SqliteUnitOfWork:
    return SqliteUnitOfWork(conn)


@pytest.fixture
def clock() -> ControllableClock:
    return ControllableClock(NOW)


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def register(
    uow: UnitOfWork, clock: ControllableClock, key: object = "key-1", **changes: object
):
    return register_account(uow, clock, REGISTRAR, key, {**BODY, **changes})


def test_registration_creates_one_zero_state_open_account(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    result = register(uow, clock)
    assert isinstance(result, Success) and result.replayed is False
    assert result.value.status == 201
    account = result.value.data["account"]
    assert account == {  # type: ignore[comparison-overlap]
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
    assert result.value.data["registration_state"] == "created"
    assert counts(conn) == {
        "accounts": 1,
        "retention_metadata": 1,
        "audit_trace": 1,
        "idempotency_outcomes": 1,
        "movements": 0,
        "holds": 0,
        "ledger_entries": 0,
        "movement_evidence": 0,
    }
    row = conn.execute(
        "SELECT account_id, customer_id, currency, eligibility_reference, status,"
        " current_balance_cents, restriction, restriction_decision_reference, created_at, closed_at"
        " FROM accounts"
    ).fetchone()
    assert row == (
        "acct-1",
        "cust-1",
        "USD",
        "elig-1",
        "open",
        0,
        "none",
        None,
        "2026-10-09T12:00:00Z",
        None,
    )
    retention = conn.execute(
        "SELECT account_id, record_type, record_id, final_at, eligible_after, legal_hold,"
        " legal_hold_decision_reference FROM retention_metadata"
    ).fetchone()
    assert retention == ("acct-1", "account", "acct-1", None, None, 0, None)
    trace = conn.execute(
        "SELECT account_id, instruction_id, operation, outcome, caller_id, caller_role,"
        " correlation_id, movement_id, ledger_entry_id, occurred_at FROM audit_trace"
    ).fetchone()
    assert trace == (
        "acct-1",
        "ins-1",
        "register_account",
        "accepted",
        "registrar-1",
        "account_registrar",
        "corr-1",
        None,
        None,
        "2026-10-09T12:00:00Z",
    )


def test_same_key_and_request_replays_the_original_outcome_without_new_rows(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    first = register(uow, clock)
    before = counts(conn)
    clock.advance(3600)  # a replay must not rewrite times or rows
    second = register(uow, clock)
    assert isinstance(first, Success) and isinstance(second, Success)
    assert second.replayed is True and second.value == first.value
    assert counts(conn) == before


def test_duplicate_account_or_customer_is_rejected_without_extra_business_rows(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    register(uow, clock)
    before = counts(conn)
    same_account = register(
        uow, clock, "key-2", customer_id="cust-2", instruction_id="ins-2"
    )
    same_customer = register(
        uow, clock, "key-3", account_id="acct-2", instruction_id="ins-3"
    )
    for result in (same_account, same_customer):
        assert isinstance(result, Failure)
        assert (
            result.error.code == "DUPLICATE_ACCOUNT" and result.error.retryable is False
        )
        assert result.replayed is False
    after = counts(conn)
    # only the deterministic rejection outcomes are stored (DEC-0011)
    assert after["idempotency_outcomes"] == before["idempotency_outcomes"] + 2
    assert {k: v for k, v in after.items() if k != "idempotency_outcomes"} == {
        k: v for k, v in before.items() if k != "idempotency_outcomes"
    }
    stored = conn.execute(
        "SELECT outcome_class, http_status FROM idempotency_outcomes WHERE instruction_id = 'ins-2'"
    ).fetchone()
    assert stored == ("deterministic_rejection", 409)


def test_a_stored_rejection_replays_exactly(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    register(uow, clock)
    first = register(uow, clock, "key-2", account_id="acct-9", instruction_id="ins-9")
    before = counts(conn)
    again = register(uow, clock, "key-2", account_id="acct-9", instruction_id="ins-9")
    assert isinstance(first, Failure) and isinstance(again, Failure)
    assert again.error == first.error and again.replayed is True
    assert counts(conn) == before


def test_a_new_key_for_the_same_registration_is_a_new_duplicate_not_a_replay(
    uow: SqliteUnitOfWork, clock: ControllableClock
) -> None:
    register(uow, clock)
    result = register(uow, clock, "key-other")
    assert isinstance(result, Failure) and result.error.code == "DUPLICATE_ACCOUNT"


def test_changed_request_under_the_same_key_conflicts_and_stores_nothing(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    register(uow, clock)
    before = counts(conn)
    for change in (
        {"eligibility_reference": "elig-2"},
        {"account_id": "acct-2"},
        {"instruction_id": "ins-2"},
    ):
        result = register(uow, clock, "key-1", **change)
        assert isinstance(result, Failure)
        assert result.error.code == "IDEMPOTENCY_CONFLICT" and result.replayed is False
    assert counts(conn) == before
    original = register(uow, clock)
    assert (
        isinstance(original, Success) and original.replayed is True
    )  # original outcome intact


def test_unauthorized_caller_never_reaches_storage(clock: ControllableClock) -> None:
    class Forbidden:
        def write(self):
            raise AssertionError("storage must not be touched before authorization")

    for role in ("account_reader", "payment_orchestrator", "nobody"):
        caller = CallerContext("c-1", role, "corr-1", "acct-1")
        result = register_account(Forbidden(), clock, caller, "key-1", BODY)  # type: ignore[arg-type]
        assert isinstance(result, Failure) and result.error.code == "FORBIDDEN_SCOPE"


def test_invalid_requests_are_not_stored_and_have_no_effect(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    bad_bodies: list[object] = [
        {k: v for k, v in BODY.items() if k != "currency"},
        {**BODY, "caller_id": "someone"},
        {**BODY, "currency": "EUR"},
        {**BODY, "currency": "usd"},
        {**BODY, "account_id": "bad id"},
        {**BODY, "customer_id": ""},
        {**BODY, "instruction_id": "x" * 129},
        {**BODY, "eligibility_reference": None},
        {**BODY, "account_id": 5},
        [],
        None,
        "text",
    ]
    for body in bad_bodies:
        result = register_account(uow, clock, REGISTRAR, "key-1", body)
        assert (
            isinstance(result, Failure) and result.error.code == "VALIDATION_ERROR"
        ), body
    for key in (None, "", "bad key", "x" * 129, 7, b"key"):
        result = register(uow, clock, key)
        assert (
            isinstance(result, Failure) and result.error.code == "VALIDATION_ERROR"
        ), key
    assert all(count == 0 for count in counts(conn).values())


def test_clock_failure_rejects_the_instruction_without_effect(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection
) -> None:
    class Broken:
        def now(self) -> datetime:
            raise RuntimeError("clock down")

    result = register_account(uow, Broken(), REGISTRAR, "key-1", BODY)  # type: ignore[arg-type]
    assert isinstance(result, Failure) and result.error.code == "SERVICE_UNREADY"
    assert all(count == 0 for count in counts(conn).values())


class FailingAfter:
    """Wraps a unit of work and raises after the n-th storage call (fault injection)."""

    def __init__(self, inner: SqliteUnitOfWork, fail_after: int) -> None:
        self.inner = inner
        self.fail_after = fail_after
        self.calls = 0

    @contextmanager
    def write(self) -> Iterator[WriteTransaction]:
        with self.inner.write() as tx:
            yield _Tracked(tx, self)  # type: ignore[misc]


class _Tracked:
    def __init__(self, tx: WriteTransaction, owner: FailingAfter) -> None:
        self._tx = tx
        self._owner = owner

    def __getattr__(self, name: str):
        target = getattr(self._tx, name)

        def call(*args: object, **kwargs: object) -> object:
            if self._owner.calls == self._owner.fail_after:
                raise RuntimeError(f"injected before {name}")
            self._owner.calls += 1
            return target(*args, **kwargs)

        return call


def test_failure_after_every_persistence_step_leaves_all_effects_or_none(
    db_path: pathlib.Path, clock: ControllableClock
) -> None:
    steps = 5  # find_outcome, registration_taken, create_account, append_trace, save_outcome
    for fail_after in range(steps):
        conn = open_database(db_path)
        wrapped = FailingAfter(SqliteUnitOfWork(conn), fail_after)
        # an unexpected error is a safe INTERNAL_ERROR, never a raw exception (TEST-28)
        result = register_account(wrapped, clock, REGISTRAR, "key-1", BODY)  # type: ignore[arg-type]
        assert isinstance(result, Failure) and result.error.code == "INTERNAL_ERROR", (
            fail_after
        )
        assert all(c == 0 for c in counts(conn).values()), fail_after
        conn.close()
    # with no injected failure the same request then succeeds, so nothing was half-claimed
    conn = open_database(db_path)
    ok = register_account(SqliteUnitOfWork(conn), clock, REGISTRAR, "key-1", BODY)
    assert isinstance(ok, Success) and ok.replayed is False
    assert counts(conn)["accounts"] == 1


def test_transient_failure_is_rolled_back_and_not_stored(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    def work(tx: WriteTransaction, now: str) -> Success[Response] | Failure:
        tx.create_account(
            NewAccount("a", "c", "e"),
            now,
        )
        return failure("SERVICE_BUSY", "Retry.", retryable=True)

    result = run_idempotent(
        uow,
        clock,
        scope="s",
        key="k",
        fingerprint="f" * 64,
        instruction_id="i",
        work=work,
    )
    assert isinstance(result, Failure) and result.error.code == "SERVICE_BUSY"
    assert all(
        count == 0 for count in counts(conn).values()
    )  # effects and outcome both gone


def test_busy_database_gives_a_retryable_failure_and_stores_nothing(
    db_path: pathlib.Path, clock: ControllableClock
) -> None:
    holder = open_database(db_path)
    victim = open_database(db_path, busy_timeout_ms=50)
    with write_transaction(holder):
        result = register_account(
            SqliteUnitOfWork(victim), clock, REGISTRAR, "key-1", BODY
        )
    assert isinstance(result, Failure)
    assert result.error.code == "SERVICE_BUSY" and result.error.retryable is True
    assert all(count == 0 for count in counts(open_database(db_path)).values())


def test_concurrent_registrations_of_one_customer_create_exactly_one_account(
    db_path: pathlib.Path, clock: ControllableClock
) -> None:
    results: list[object] = []
    lock = threading.Lock()

    def attempt(n: int) -> None:
        conn = open_database(db_path, busy_timeout_ms=10_000)
        outcome = register_account(
            SqliteUnitOfWork(conn),
            clock,
            REGISTRAR,
            f"key-{n}",
            {**BODY, "account_id": f"acct-{n}", "instruction_id": f"ins-{n}"},
        )
        conn.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wins = [r for r in results if isinstance(r, Success)]
    losses = [r for r in results if isinstance(r, Failure)]
    assert len(wins) == 1 and len(losses) == 5
    assert {r.error.code for r in losses} == {"DUPLICATE_ACCOUNT"}
    check = open_database(db_path)
    assert counts(check)["accounts"] == 1 and counts(check)["audit_trace"] == 1


def test_scope_keys_are_deterministic_and_fit_the_stored_alphabet() -> None:
    long_id = "c" * 128
    scope = scope_key(long_id, "register_account")
    assert scope == scope_key(long_id, "register_account")
    assert len(scope) == 64 and set(scope) <= set("0123456789abcdef")
    assert len({scope_key("a", "op"), scope_key("b", "op"), scope_key("a", "op2")}) == 3
    assert scope_key("ab", "c") != scope_key(
        "a", "bc"
    )  # the pair boundary is unambiguous
