"""Approved correction: append-only, decision-linked, negative-balance permitted (FR-09, API-16, TEST-09)."""

from __future__ import annotations

import pathlib
import sqlite3

from abm.application.caller import CallerContext
from abm.application.corrections import create_correction
from abm.domain.results import Failure, Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from tests.integration.store_support import clock, fund, open_started, register

CORRECTOR = CallerContext("corr-1", "correction_authority", "corr-x")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")


def body(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "instruction_id": "ins-c1",
        "correction_id": "cor-1",
        "direction": "credit",
        "amount_cents": 500,
        "currency": "USD",
        "decision_reference": "dec-1",
    }
    base.update(overrides)
    return base


def setup(tmp_path: pathlib.Path) -> tuple[sqlite3.Connection, SqliteUnitOfWork]:
    conn = open_started(tmp_path / "abm.sqlite3")
    uow, now = SqliteUnitOfWork(conn), clock()
    register(uow, now, "acct-a")
    register(uow, now, "acct-b")
    fund(uow, now, "acct-a", 1000)
    return conn, uow


def balance(conn: sqlite3.Connection, account: str) -> int:
    row = conn.execute(
        "SELECT current_balance_cents FROM accounts WHERE account_id = ?", (account,)
    ).fetchone()
    return row[0]


def ledger_rows(conn: sqlite3.Connection) -> list[tuple[object, ...]]:
    return conn.execute(
        "SELECT entry_id, account_id, movement_id, effect_kind, direction, amount_cents,"
        " correction_of_entry_id FROM ledger_entries ORDER BY sequence"
    ).fetchall()


def settlement_entry(conn: sqlite3.Connection, account: str) -> str:
    row = conn.execute(
        "SELECT entry_id FROM ledger_entries WHERE account_id = ? AND effect_kind = 'incoming_settlement'",
        (account,),
    ).fetchone()
    return row[0]


def test_credit_correction_appends_one_linked_entry_and_keeps_history(tmp_path):
    conn, uow = setup(tmp_path)
    before = ledger_rows(conn)
    result = create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-a", body())

    assert isinstance(result, Success)
    assert result.value.status == 201
    assert result.value.data["movement_type"] == "correction"
    assert result.value.data["accounts"][0]["current_balance_cents"] == 1500
    assert balance(conn, "acct-a") == 1500

    after = ledger_rows(conn)
    assert after[: len(before)] == before  # original entries unchanged
    assert len(after) == len(before) + 1
    assert after[-1][1:6] == ("acct-a", "cor-1", "correction", "credit", 500)

    trace = conn.execute(
        "SELECT operation, external_reference FROM audit_trace WHERE operation = 'correction'"
    ).fetchall()
    assert trace == [("correction", "dec-1")]
    stored = conn.execute(
        "SELECT decision_reference FROM movements WHERE movement_id = 'cor-1'"
    ).fetchone()
    assert stored == ("dec-1",)


def test_debit_correction_may_make_the_balance_negative(tmp_path):
    conn, uow = setup(tmp_path)
    # a risk restriction is set (direct SQL; the risk-restriction command is TASK-20)
    conn.execute(
        "UPDATE accounts SET restriction = 'outgoing_blocked',"
        " restriction_decision_reference = 'dec-r' WHERE account_id = 'acct-a'"
    )
    result = create_correction(
        uow,
        clock(),
        CORRECTOR,
        "key-c1",
        "acct-a",
        body(direction="debit", amount_cents=1800),
    )

    assert isinstance(result, Success)
    assert result.value.data["accounts"][0]["current_balance_cents"] == -800
    assert balance(conn, "acct-a") == -800


def test_correction_may_name_a_corrected_entry_on_the_same_account(tmp_path):
    conn, uow = setup(tmp_path)
    original = settlement_entry(conn, "acct-a")
    result = create_correction(
        uow,
        clock(),
        CORRECTOR,
        "key-c1",
        "acct-a",
        body(corrected_entry_reference=original),
    )

    assert isinstance(result, Success)
    stored = conn.execute(
        "SELECT correction_of_entry_id FROM ledger_entries WHERE effect_kind = 'correction'"
    ).fetchone()
    assert stored == (original,)


def test_exact_replay_returns_the_stored_result_without_a_second_effect(tmp_path):
    conn, uow = setup(tmp_path)
    first = create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-a", body())
    entries = len(ledger_rows(conn))
    replay = create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-a", body())

    assert isinstance(replay, Success)
    assert replay.replayed is True
    assert replay.value.data == first.value.data
    assert len(ledger_rows(conn)) == entries
    assert balance(conn, "acct-a") == 1500


def test_same_key_with_a_different_request_is_a_conflict_without_effect(tmp_path):
    conn, uow = setup(tmp_path)
    create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-a", body())
    entries = len(ledger_rows(conn))
    result = create_correction(
        uow, clock(), CORRECTOR, "key-c1", "acct-a", body(amount_cents=501)
    )

    assert isinstance(result, Failure)
    assert result.error.code == "IDEMPOTENCY_CONFLICT"
    assert len(ledger_rows(conn)) == entries
    assert balance(conn, "acct-a") == 1500


def test_reused_correction_id_is_refused_without_effect(tmp_path):
    conn, uow = setup(tmp_path)
    create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-a", body())
    entries = len(ledger_rows(conn))
    result = create_correction(
        uow,
        clock(),
        CORRECTOR,
        "key-c2",
        "acct-a",
        body(instruction_id="ins-c2", decision_reference="dec-2"),
    )

    assert isinstance(result, Failure)
    assert result.error.code == "INVALID_TRANSITION"
    assert len(ledger_rows(conn)) == entries
    assert balance(conn, "acct-a") == 1500


def test_reused_decision_is_refused_without_effect(tmp_path):
    conn, uow = setup(tmp_path)
    create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-a", body())
    entries = len(ledger_rows(conn))
    result = create_correction(
        uow,
        clock(),
        CORRECTOR,
        "key-c2",
        "acct-a",
        body(instruction_id="ins-c2", correction_id="cor-2"),
    )

    assert isinstance(result, Failure)
    assert result.error.code == "INVALID_TRANSITION"
    assert len(ledger_rows(conn)) == entries
    assert balance(conn, "acct-a") == 1500


def test_corrected_entry_of_another_account_or_unknown_is_refused(tmp_path):
    conn, uow = setup(tmp_path)
    fund(uow, clock(), "acct-b", 300)
    other = settlement_entry(conn, "acct-b")
    entries = len(ledger_rows(conn))

    for corrected in (other, "no-such-entry"):
        result = create_correction(
            uow,
            clock(),
            CORRECTOR,
            f"key-{corrected}",
            "acct-a",
            body(corrected_entry_reference=corrected),
        )
        assert isinstance(result, Failure)
        assert result.error.code == "INVALID_TRANSITION"

    assert len(ledger_rows(conn)) == entries
    assert balance(conn, "acct-a") == 1000


def test_unknown_account_is_not_found(tmp_path):
    _conn, uow = setup(tmp_path)
    result = create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-zz", body())

    assert isinstance(result, Failure)
    assert result.error.code == "ACCOUNT_NOT_FOUND"


def test_invalid_direction_is_a_validation_error_not_stored(tmp_path):
    conn, uow = setup(tmp_path)
    result = create_correction(
        uow, clock(), CORRECTOR, "key-c1", "acct-a", body(direction="both")
    )

    assert isinstance(result, Failure)
    assert result.error.code == "VALIDATION_ERROR"
    assert balance(conn, "acct-a") == 1000
    # nothing was stored, so the same key can be used with a valid request
    retry = create_correction(uow, clock(), CORRECTOR, "key-c1", "acct-a", body())
    assert isinstance(retry, Success)


def test_other_roles_and_extra_fields_are_refused(tmp_path):
    conn, uow = setup(tmp_path)
    denied = create_correction(uow, clock(), PAYER, "key-c1", "acct-a", body())
    extra = create_correction(
        uow, clock(), CORRECTOR, "key-c2", "acct-a", body(note="free text")
    )

    assert isinstance(denied, Failure)
    assert denied.error.code == "FORBIDDEN_SCOPE"
    assert isinstance(extra, Failure)
    assert extra.error.code == "VALIDATION_ERROR"
    assert balance(conn, "acct-a") == 1000
