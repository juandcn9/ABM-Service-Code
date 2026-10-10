"""Closure: eligibility, terminal state, closed-account refusals and permitted late evidence (INV-15, INV-16, TEST-13)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

from abm.application.caller import CallerContext
from abm.application.cards import authorize_card, clear_card, refund_card, reverse_card
from abm.application.closure import close_account
from abm.application.corrections import create_correction
from abm.application.incoming_ach import (
    create_incoming_ach,
    return_incoming_ach,
    settle_incoming_ach,
)
from abm.application.outgoing_ach import create_outgoing_ach, submit_outgoing_ach
from abm.application.risk import set_risk_restriction
from abm.application.transfers import internal_transfer
from abm.domain.results import Failure, Success
from abm.persistence.readiness import readiness_reasons
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import (
    MIGRATIONS,
    clock,
    fund,
    open_started,
    register,
)

REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")
RISK = CallerContext("risk-1", "risk_controller", "corr-r")
CORRECTOR = CallerContext("corr-1", "correction_authority", "corr-x")


def setup(tmp_path: pathlib.Path) -> tuple[sqlite3.Connection, SqliteUnitOfWork]:
    conn = open_started(tmp_path / "abm.sqlite3")
    uow, now = SqliteUnitOfWork(conn), clock()
    register(uow, now, "acct-a")
    register(uow, now, "acct-b")
    fund(uow, now, "acct-a", 1000)
    return conn, uow


def close(uow, key="k-close", instruction="ins-close"):
    return close_account(
        uow, clock(), REGISTRAR, key, "acct-a", {"instruction_id": instruction}
    )


def drain_to_zero(uow, cents: int = 1000) -> None:
    """Move the whole current balance of acct-a to acct-b, so acct-a's balance is zero."""
    result = internal_transfer(
        uow,
        clock(),
        PAYER,
        "k-drain",
        {
            "instruction_id": "ins-drain",
            "movement_id": "mv-drain",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": cents,
            "currency": "USD",
        },
    )
    assert isinstance(result, Success)


def status_of(
    conn: sqlite3.Connection, account: str = "acct-a"
) -> tuple[str, str | None]:
    return conn.execute(
        "SELECT status, closed_at FROM accounts WHERE account_id = ?", (account,)
    ).fetchone()


def balance(conn: sqlite3.Connection, account: str = "acct-a") -> int:
    return conn.execute(
        "SELECT current_balance_cents FROM accounts WHERE account_id = ?", (account,)
    ).fetchone()[0]


def closure_traces(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM audit_trace WHERE operation = 'close_account'"
    ).fetchone()[0]


def test_eligible_closure_is_terminal_and_keeps_the_restriction(tmp_path):
    conn, uow = setup(tmp_path)
    drain_to_zero(uow)  # the block would refuse the transfer, so drain first
    set_risk_restriction(
        uow,
        clock(),
        RISK,
        "k-r",
        "acct-a",
        {"instruction_id": "ins-r", "action": "set", "decision_reference": "dec-r"},
    )
    result = close(uow)

    assert isinstance(result, Success)
    assert result.value.status == 200
    assert result.value.data == {"account_id": "acct-a", "status": "closed"}
    assert status_of(conn)[0] == "closed" and status_of(conn)[1] is not None
    assert conn.execute(
        "SELECT restriction FROM accounts WHERE account_id = 'acct-a'"
    ).fetchone() == ("outgoing_blocked",)
    assert closure_traces(conn) == 1

    again = close(uow, key="k-close-2", instruction="ins-close-2")
    assert isinstance(again, Failure) and again.error.code == "INVALID_TRANSITION"
    assert closure_traces(conn) == 1


def test_a_nonzero_balance_blocks_closure_and_writes_nothing(tmp_path):
    conn, uow = setup(tmp_path)
    result = close(uow)

    assert isinstance(result, Failure)
    assert result.error.code == "CLOSURE_PRECONDITION_FAILED"
    assert status_of(conn)[0] == "open"
    assert closure_traces(conn) == 0


def test_an_active_hold_blocks_closure_even_at_zero_balance(tmp_path):
    conn, uow = setup(tmp_path)
    authorize_card(
        uow,
        clock(),
        CARD,
        "k-auth",
        "acct-a",
        {
            "instruction_id": "ins-auth",
            "movement_id": "mv-hold",
            "amount_cents": 400,
            "currency": "USD",
            "external_reference": "ext-hold",
            "merchant_reference": "m-1",
        },
    )
    # a debit correction brings the current balance to zero; the 400 hold stays active
    create_correction(
        uow,
        clock(),
        CORRECTOR,
        "k-corr",
        "acct-a",
        {
            "instruction_id": "ins-corr",
            "correction_id": "cor-zero",
            "direction": "debit",
            "amount_cents": 1000,
            "currency": "USD",
            "decision_reference": "dec-zero",
        },
    )
    assert balance(conn) == 0

    result = close(uow)
    assert isinstance(result, Failure)
    assert result.error.code == "CLOSURE_PRECONDITION_FAILED"
    assert status_of(conn)[0] == "open"


def test_an_unresolved_movement_blocks_closure(tmp_path):
    conn, uow = setup(tmp_path)
    drain_to_zero(uow)
    notice = create_incoming_ach(
        uow,
        clock(),
        PAYER,
        "k-notice",
        "acct-a",
        {
            "instruction_id": "ins-notice",
            "movement_id": "mv-notice",
            "amount_cents": 200,
            "currency": "USD",
            "external_reference": "ext-notice",
        },
    )
    assert isinstance(notice, Success)  # pending: no balance effect

    result = close(uow)
    assert isinstance(result, Failure)
    assert result.error.code == "CLOSURE_PRECONDITION_FAILED"
    assert status_of(conn)[0] == "open"


def test_a_movement_awaiting_settlement_blocks_closure(tmp_path):
    conn, uow = setup(tmp_path)
    create_outgoing_ach(
        uow,
        clock(),
        PAYER,
        "k-out",
        "acct-a",
        {
            "instruction_id": "ins-out",
            "movement_id": "mv-out",
            "amount_cents": 400,
            "currency": "USD",
            "external_reference": "ext-out",
            "destination_reference": "dest-1",
        },
    )
    create_correction(
        uow,
        clock(),
        CORRECTOR,
        "k-corr",
        "acct-a",
        {
            "instruction_id": "ins-corr",
            "correction_id": "cor-zero",
            "direction": "debit",
            "amount_cents": 1000,
            "currency": "USD",
            "decision_reference": "dec-zero",
        },
    )
    # balance is zero, and the outgoing movement is still accepted_with_hold
    result = close(uow)
    assert isinstance(result, Failure)
    assert result.error.code == "CLOSURE_PRECONDITION_FAILED"
    assert status_of(conn)[0] == "open"


def test_a_submitted_outgoing_movement_blocks_closure(tmp_path):
    conn, uow = setup(tmp_path)
    create_outgoing_ach(
        uow,
        clock(),
        PAYER,
        "k-out",
        "acct-a",
        {
            "instruction_id": "ins-out",
            "movement_id": "mv-out",
            "amount_cents": 400,
            "currency": "USD",
            "external_reference": "ext-out",
            "destination_reference": "dest-1",
        },
    )
    submitted = submit_outgoing_ach(
        uow,
        clock(),
        PAYER,
        "k-submit",
        "acct-a",
        "mv-out",
        {"instruction_id": "ins-submit", "evidence_reference": "ev-submit"},
    )
    assert isinstance(submitted, Success)
    create_correction(
        uow,
        clock(),
        CORRECTOR,
        "k-corr",
        "acct-a",
        {
            "instruction_id": "ins-corr",
            "correction_id": "cor-zero",
            "direction": "debit",
            "amount_cents": 1000,
            "currency": "USD",
            "decision_reference": "dec-zero",
        },
    )

    result = close(uow)
    assert isinstance(result, Failure)
    assert result.error.code == "CLOSURE_PRECONDITION_FAILED"
    assert status_of(conn)[0] == "open"


def test_incoming_settlement_refuses_a_closed_account_before_writes(tmp_path):
    conn, uow = setup(tmp_path)
    notice = create_incoming_ach(
        uow,
        clock(),
        PAYER,
        "k-notice",
        "acct-a",
        {
            "instruction_id": "ins-notice",
            "movement_id": "mv-pending",
            "amount_cents": 200,
            "currency": "USD",
            "external_reference": "ext-pending",
        },
    )
    assert isinstance(notice, Success)
    conn.execute(
        "UPDATE accounts SET status = 'closed', closed_at = ? WHERE account_id = 'acct-a'",
        ("2026-10-10T12:00:00Z",),
    )
    before = (
        balance(conn),
        conn.execute(
            "SELECT state FROM movements WHERE movement_id = 'mv-pending'"
        ).fetchone(),
        conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone(),
        conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone(),
    )

    result = settle_incoming_ach(
        uow,
        clock(),
        PAYER,
        "k-settle",
        "acct-a",
        "mv-pending",
        {"instruction_id": "ins-settle", "evidence_reference": "ev-settle"},
    )

    assert isinstance(result, Failure) and result.error.code == "ACCOUNT_CLOSED"
    assert (
        balance(conn),
        conn.execute(
            "SELECT state FROM movements WHERE movement_id = 'mv-pending'"
        ).fetchone(),
        conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone(),
        conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone(),
    ) == before


def test_a_closed_account_refuses_new_customer_instructions(tmp_path):
    conn, uow = setup(tmp_path)
    drain_to_zero(uow)
    assert isinstance(close(uow), Success)
    now = clock()

    refused = [
        authorize_card(
            uow,
            now,
            CARD,
            "k-c1",
            "acct-a",
            {
                "instruction_id": "ins-c1",
                "movement_id": "mv-c1",
                "amount_cents": 1,
                "currency": "USD",
                "external_reference": "ext-c1",
                "merchant_reference": "m-1",
            },
        ),
        create_outgoing_ach(
            uow,
            now,
            PAYER,
            "k-o1",
            "acct-a",
            {
                "instruction_id": "ins-o1",
                "movement_id": "mv-o1",
                "amount_cents": 1,
                "currency": "USD",
                "external_reference": "ext-o1",
                "destination_reference": "dest-1",
            },
        ),
        internal_transfer(
            uow,
            now,
            PAYER,
            "k-t1",
            {
                "instruction_id": "ins-t1",
                "movement_id": "mv-t1",
                "source_account_id": "acct-b",
                "destination_account_id": "acct-a",
                "amount_cents": 1,
                "currency": "USD",
            },
        ),
        create_incoming_ach(
            uow,
            now,
            PAYER,
            "k-i1",
            "acct-a",
            {
                "instruction_id": "ins-i1",
                "movement_id": "mv-i1",
                "amount_cents": 1,
                "currency": "USD",
                "external_reference": "ext-i1",
            },
        ),
    ]
    for result in refused:
        assert isinstance(result, Failure)
        assert result.error.code == "ACCOUNT_CLOSED"
    assert status_of(conn)[0] == "closed"


def test_permitted_late_evidence_after_closure_does_not_reopen_the_account(tmp_path):
    conn, uow = setup(tmp_path)
    # a card movement is reversed, then the account is drained and closed
    authorize_card(
        uow,
        clock(),
        CARD,
        "k-auth",
        "acct-a",
        {
            "instruction_id": "ins-auth",
            "movement_id": "mv-late",
            "amount_cents": 400,
            "currency": "USD",
            "external_reference": "ext-late",
            "merchant_reference": "m-1",
        },
    )
    reverse_card(
        uow,
        clock(),
        CARD,
        "k-rev",
        "acct-a",
        "mv-late",
        {"instruction_id": "ins-rev", "evidence_reference": "ev-rev"},
    )
    drain_to_zero(uow)
    assert isinstance(close(uow), Success)

    late = clear_card(
        uow,
        clock(),
        CARD,
        "k-late",
        "acct-a",
        "mv-late",
        {
            "instruction_id": "ins-late",
            "evidence_reference": "ev-late",
            "amount_cents": 400,
            "currency": "USD",
        },
    )
    assert isinstance(late, Success) and late.value.data["state"] == "late_cleared"

    refund = refund_card(
        uow,
        clock(),
        CARD,
        "k-refund",
        "acct-a",
        "mv-late",
        {
            "instruction_id": "ins-refund",
            "evidence_reference": "ev-refund",
            "amount_cents": 400,
            "currency": "USD",
        },
    )
    assert isinstance(refund, Success)

    # the incoming settlement is returned in full after closure (permitted return)
    back = return_incoming_ach(
        uow,
        clock(),
        PAYER,
        "k-back",
        "acct-a",
        "mv-in-acct-a",
        {
            "instruction_id": "ins-back",
            "evidence_reference": "ev-back",
            "amount_cents": 1000,
            "currency": "USD",
        },
    )
    assert isinstance(back, Success)

    corrected = create_correction(
        uow,
        clock(),
        CORRECTOR,
        "k-corr-c",
        "acct-a",
        {
            "instruction_id": "ins-corr-c",
            "correction_id": "cor-c",
            "direction": "credit",
            "amount_cents": 50,
            "currency": "USD",
            "decision_reference": "dec-c",
        },
    )
    assert isinstance(corrected, Success)

    assert status_of(conn)[0] == "closed"
    assert readiness_reasons(conn, MIGRATIONS) == []


def test_a_restriction_is_accepted_on_a_closed_account(tmp_path):
    conn, uow = setup(tmp_path)
    drain_to_zero(uow)
    assert isinstance(close(uow), Success)

    result = set_risk_restriction(
        uow,
        clock(),
        RISK,
        "k-r-closed",
        "acct-a",
        {
            "instruction_id": "ins-r-closed",
            "action": "set",
            "decision_reference": "dec-r",
        },
    )
    assert isinstance(result, Success)
    assert status_of(conn)[0] == "closed"


def test_a_post_closure_settlement_is_reported_by_readiness(tmp_path):
    conn, uow = setup(tmp_path)
    drain_to_zero(uow)
    assert isinstance(close(uow), Success)
    assert readiness_reasons(conn, MIGRATIONS) == []

    # a settlement can only be written outside the commands; readiness must refuse it
    conn.execute(
        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind,"
        " direction, amount_cents, authorized_caller_id, authorized_role, created_at)"
        " VALUES ('forbidden-after-close', 'acct-a', 'mv-drain', 'outgoing_settlement',"
        " 'debit', 1, 'pay-1', 'payment_orchestrator', '2026-10-10T13:00:00Z')"
    )
    # Keep the account projection consistent so only the post-closure settlement clause fails.
    conn.execute(
        "UPDATE accounts SET current_balance_cents = -1 WHERE account_id = 'acct-a'"
    )
    assert "INTEGRITY_FAILED" in readiness_reasons(conn, MIGRATIONS)


def test_closure_by_another_role_or_an_unknown_account_is_refused(tmp_path):
    conn, uow = setup(tmp_path)
    wrong_role = close_account(
        uow, clock(), PAYER, "k-w", "acct-a", {"instruction_id": "ins-w"}
    )
    unknown = close_account(
        uow, clock(), REGISTRAR, "k-u", "acct-zz", {"instruction_id": "ins-u"}
    )

    assert (
        isinstance(wrong_role, Failure) and wrong_role.error.code == "FORBIDDEN_SCOPE"
    )
    assert isinstance(unknown, Failure) and unknown.error.code == "ACCOUNT_NOT_FOUND"
    assert status_of(conn)[0] == "open"


def test_replay_returns_the_stored_closure_without_a_second_trace(tmp_path):
    conn, uow = setup(tmp_path)
    drain_to_zero(uow)
    first = close(uow)
    replay = close(uow)

    assert isinstance(replay, Success) and replay.replayed is True
    assert replay.value.data == first.value.data
    assert closure_traces(conn) == 1


def test_late_clearing_then_refund_after_closure_is_clean_with_time_advancing(tmp_path):
    """The clock moves after closure, so late effects are strictly later than closed_at (readiness)."""
    ticking = ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
    conn, uow = setup(tmp_path)
    authorize_card(
        uow,
        ticking,
        CARD,
        "k-auth",
        "acct-a",
        {
            "instruction_id": "ins-auth",
            "movement_id": "mv-late",
            "amount_cents": 400,
            "currency": "USD",
            "external_reference": "ext-late",
            "merchant_reference": "m-1",
        },
    )
    reverse_card(
        uow,
        ticking,
        CARD,
        "k-rev",
        "acct-a",
        "mv-late",
        {"instruction_id": "ins-rev", "evidence_reference": "ev-rev"},
    )
    drain_to_zero(uow)
    ticking.advance(60)
    assert isinstance(
        close_account(
            uow,
            ticking,
            REGISTRAR,
            "k-close",
            "acct-a",
            {"instruction_id": "ins-close"},
        ),
        Success,
    )

    ticking.advance(60)
    late = clear_card(
        uow,
        ticking,
        CARD,
        "k-late",
        "acct-a",
        "mv-late",
        {
            "instruction_id": "ins-late",
            "evidence_reference": "ev-late",
            "amount_cents": 400,
            "currency": "USD",
        },
    )
    assert isinstance(late, Success)
    assert readiness_reasons(conn, MIGRATIONS) == []

    ticking.advance(60)
    refund = refund_card(
        uow,
        ticking,
        CARD,
        "k-refund",
        "acct-a",
        "mv-late",
        {
            "instruction_id": "ins-refund",
            "evidence_reference": "ev-refund",
            "amount_cents": 400,
            "currency": "USD",
        },
    )
    assert isinstance(refund, Success)
    assert conn.execute(
        "SELECT state FROM movements WHERE movement_id = 'mv-late'"
    ).fetchone() == ("refunded",)
    assert readiness_reasons(conn, MIGRATIONS) == []
