"""Legal-hold refusals that must stay stored or write nothing (TEST-45)."""

from __future__ import annotations

from datetime import UTC, datetime

from abm.application.caller import CallerContext
from abm.application.legal_hold import set_legal_hold
from abm.domain.results import Failure, Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import open_started, register

RETENTION = CallerContext("ret-1", "retention_controller", "corr-t")
START = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)


def body(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "instruction_id": "ins-h",
        "record_type": "account",
        "record_id": "acct-a",
        "action": "set",
        "decision_reference": "dec-h",
    }
    base.update(overrides)
    return base


def test_a_same_key_replay_of_a_stored_refusal_returns_the_refusal_without_effect(
    tmp_path,
):
    clock = ControllableClock(START)
    conn = open_started(tmp_path / "abm.sqlite3")
    uow = SqliteUnitOfWork(conn)
    register(uow, clock, "acct-a")

    first = set_legal_hold(uow, clock, RETENTION, "k-h", "acct-a", body())
    refused = set_legal_hold(
        uow, clock, RETENTION, "k-h2", "acct-a", body(instruction_id="ins-h2")
    )
    replay = set_legal_hold(
        uow, clock, RETENTION, "k-h2", "acct-a", body(instruction_id="ins-h2")
    )

    assert isinstance(first, Success)
    assert isinstance(refused, Failure) and refused.error.code == "INVALID_TRANSITION"
    assert isinstance(replay, Failure) and replay.replayed is True
    assert replay.error.code == "INVALID_TRANSITION"
    assert conn.execute(
        "SELECT COUNT(*) FROM audit_trace WHERE operation = 'legal_hold'"
    ).fetchone() == (1,)


def test_a_record_type_other_than_account_is_refused_without_effect(tmp_path):
    clock = ControllableClock(START)
    conn = open_started(tmp_path / "abm.sqlite3")
    uow = SqliteUnitOfWork(conn)
    register(uow, clock, "acct-a")

    result = set_legal_hold(
        uow, clock, RETENTION, "k-type", "acct-a", body(record_type="card")
    )

    assert isinstance(result, Failure) and result.error.code == "VALIDATION_ERROR"
    assert conn.execute(
        "SELECT legal_hold FROM retention_metadata WHERE account_id = 'acct-a'"
    ).fetchone() == (0,)
