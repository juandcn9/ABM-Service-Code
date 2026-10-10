"""Retention dates, seven-year evaluation and the non-public legal-hold port (FR-16, TEST-19, TEST-45)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

from abm.application.caller import CallerContext
from abm.application.closure import close_account
from abm.application.incoming_ach import return_incoming_ach
from abm.application.legal_hold import set_legal_hold
from abm.application.retention import evaluate
from abm.application.transfers import internal_transfer
from abm.domain.results import Failure, Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import fund, open_started, register

REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
RETENTION = CallerContext("ret-1", "retention_controller", "corr-t")
START = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
T0 = "2026-10-10T12:00:00Z"
T7 = "2033-10-10T12:00:00Z"


def setup(tmp_path: pathlib.Path, clock: ControllableClock):
    conn = open_started(tmp_path / "abm.sqlite3")
    uow = SqliteUnitOfWork(conn)
    register(uow, clock, "acct-a")
    register(uow, clock, "acct-b")
    fund(uow, clock, "acct-a", 1000)
    return conn, uow


def drain(uow, clock: ControllableClock) -> None:
    result = internal_transfer(
        uow,
        clock,
        PAYER,
        "k-drain",
        {
            "instruction_id": "ins-drain",
            "movement_id": "mv-drain",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": 1000,
            "currency": "USD",
        },
    )
    assert isinstance(result, Success)


def close(uow, clock: ControllableClock):
    return close_account(
        uow, clock, REGISTRAR, "k-close", "acct-a", {"instruction_id": "ins-close"}
    )


def hold(
    uow,
    clock: ControllableClock,
    action: str,
    key: str,
    instruction: str,
    record_id: str = "acct-a",
    decision: str = "dec-h",
):
    return set_legal_hold(
        uow,
        clock,
        RETENTION,
        key,
        "acct-a",
        {
            "instruction_id": instruction,
            "record_type": "account",
            "record_id": record_id,
            "action": action,
            "decision_reference": decision,
        },
    )


def give_back(uow, clock: ControllableClock, key: str = "k-back"):
    return return_incoming_ach(
        uow,
        clock,
        PAYER,
        key,
        "acct-a",
        "mv-in-acct-a",
        {
            "instruction_id": "ins-back",
            "evidence_reference": "ev-back",
            "amount_cents": 1000,
            "currency": "USD",
        },
    )


def dates(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    return conn.execute(
        "SELECT final_at, eligible_after FROM retention_metadata WHERE account_id = 'acct-a'"
    ).fetchone()


def view(uow, at: str) -> dict:
    with uow.read() as tx:
        result = evaluate(tx, "acct-a", at)
    assert result is not None
    return result


def trace_count(conn: sqlite3.Connection, operation: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM audit_trace WHERE operation = ?", (operation,)
    ).fetchone()[0]


def test_dates_are_null_until_closure(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    assert dates(conn) == (None, None)
    assert view(uow, T7)["eligible"] is False


def test_closure_sets_both_dates_seven_years_later(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    drain(uow, clock)
    assert isinstance(close(uow, clock), Success)

    assert dates(conn) == (T0, T7)
    assert view(uow, "2033-10-10T11:59:59Z")["eligible"] is False
    assert view(uow, T7)["eligible"] is True


def test_february_29_closure_maps_to_february_28(tmp_path):
    clock = ControllableClock(datetime(2028, 2, 29, 12, 0, 0, tzinfo=UTC))
    conn, uow = setup(tmp_path, clock)
    drain(uow, clock)
    assert isinstance(close(uow, clock), Success)

    assert dates(conn) == ("2028-02-29T12:00:00Z", "2035-02-28T12:00:00Z")


def test_a_permitted_late_return_after_closure_advances_both_dates(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    drain(uow, clock)
    assert isinstance(close(uow, clock), Success)
    clock.advance(2 * 365 * 24 * 3600)
    assert isinstance(give_back(uow, clock), Success)

    # 730 days after the closure (2028 is a leap year), so the late return advances the dates
    assert dates(conn) == ("2028-10-09T12:00:00Z", "2035-10-09T12:00:00Z")
    assert view(uow, "2035-10-09T11:59:59Z")["eligible"] is False
    assert view(uow, "2035-10-09T12:00:00Z")["eligible"] is True


def test_a_return_while_open_does_not_set_the_dates(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    assert isinstance(give_back(uow, clock), Success)
    assert dates(conn) == (None, None)


def test_a_legal_hold_blocks_eligibility_until_it_is_cleared(tmp_path):
    clock = ControllableClock(START)
    _conn, uow = setup(tmp_path, clock)
    drain(uow, clock)
    assert isinstance(close(uow, clock), Success)
    assert isinstance(hold(uow, clock, "set", "k-set", "ins-set"), Success)

    held = view(uow, T7)
    assert held["legal_hold"] is True and held["eligible"] is False

    cleared = hold(uow, clock, "clear", "k-clear", "ins-clear", decision="dec-c")
    assert isinstance(cleared, Success)
    assert view(uow, T7)["eligible"] is True


def test_a_legal_hold_may_precede_closure_and_dates_stay_null(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    assert isinstance(hold(uow, clock, "set", "k-set", "ins-set"), Success)
    assert dates(conn) == (None, None)
    assert view(uow, T7)["legal_hold"] is True


def test_legal_hold_set_and_clear_are_traced_and_replay_exactly(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    first = hold(uow, clock, "set", "k-set", "ins-set")
    traces = trace_count(conn, "legal_hold")
    replay = hold(uow, clock, "set", "k-set", "ins-set")

    assert isinstance(first, Success)
    assert first.value.data == {"account_id": "acct-a", "legal_hold": True}
    assert isinstance(replay, Success) and replay.replayed is True
    assert trace_count(conn, "legal_hold") == traces == 1

    again = hold(uow, clock, "set", "k-set-2", "ins-set-2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert trace_count(conn, "legal_hold") == 1


def test_legal_hold_refusals_write_nothing(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    before = trace_count(conn, "legal_hold")

    wrong_role = set_legal_hold(
        uow,
        clock,
        REGISTRAR,
        "k-role",
        "acct-a",
        {
            "instruction_id": "ins-role",
            "record_type": "account",
            "record_id": "acct-a",
            "action": "set",
            "decision_reference": "dec-h",
        },
    )
    wrong_target = hold(uow, clock, "set", "k-target", "ins-target", record_id="acct-b")
    unknown = set_legal_hold(
        uow,
        clock,
        RETENTION,
        "k-unknown",
        "acct-zz",
        {
            "instruction_id": "ins-unknown",
            "record_type": "account",
            "record_id": "acct-zz",
            "action": "set",
            "decision_reference": "dec-h",
        },
    )

    assert (
        isinstance(wrong_role, Failure) and wrong_role.error.code == "FORBIDDEN_SCOPE"
    )
    assert (
        isinstance(wrong_target, Failure)
        and wrong_target.error.code == "VALIDATION_ERROR"
    )
    assert isinstance(unknown, Failure) and unknown.error.code == "ACCOUNT_NOT_FOUND"
    assert trace_count(conn, "legal_hold") == before
    assert conn.execute(
        "SELECT legal_hold FROM retention_metadata WHERE account_id = 'acct-a'"
    ).fetchone() == (0,)


def test_a_legal_hold_fingerprint_conflict_writes_nothing(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    assert isinstance(hold(uow, clock, "set", "k-set", "ins-set"), Success)
    conflict = hold(uow, clock, "clear", "k-set", "ins-set")

    assert isinstance(conflict, Failure)
    assert conflict.error.code == "IDEMPOTENCY_CONFLICT"
    assert conn.execute(
        "SELECT legal_hold FROM retention_metadata WHERE account_id = 'acct-a'"
    ).fetchone() == (1,)
