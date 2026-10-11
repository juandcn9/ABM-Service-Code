"""Outgoing risk restriction: set/clear and enforcement (FR-10, API-17, INV-11, TEST-10)."""

from __future__ import annotations

import pathlib
import sqlite3

from abm.application.caller import CallerContext
from abm.application.cards import authorize_card
from abm.application.corrections import create_correction
from abm.application.incoming_ach import create_incoming_ach, settle_incoming_ach
from abm.application.outgoing_ach import create_outgoing_ach
from abm.application.reads import get_account
from abm.application.risk import set_risk_restriction
from abm.application.transfers import internal_transfer
from abm.domain.results import Failure, Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from tests.integration.store_support import clock, fund, open_started, register

RISK = CallerContext("risk-1", "risk_controller", "corr-r")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")
CORRECTOR = CallerContext("corr-1", "correction_authority", "corr-x")
READER = CallerContext("rd-1", "account_reader", "corr-d", account_scope="acct-a")


def body(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "instruction_id": "ins-r1",
        "action": "set",
        "decision_reference": "dec-r1",
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


def restriction_of(conn: sqlite3.Connection, account: str) -> tuple[str, str | None]:
    return conn.execute(
        "SELECT restriction, restriction_decision_reference FROM accounts WHERE account_id = ?",
        (account,),
    ).fetchone()


def balance(conn: sqlite3.Connection, account: str) -> int:
    return conn.execute(
        "SELECT current_balance_cents FROM accounts WHERE account_id = ?", (account,)
    ).fetchone()[0]


def set_block(uow, decision: str = "dec-r1", key: str = "key-r1", instruction="ins-r1"):
    return set_risk_restriction(
        uow,
        clock(),
        RISK,
        key,
        "acct-a",
        body(decision_reference=decision, instruction_id=instruction),
    )


def test_set_blocks_outgoing_and_records_the_decision(tmp_path):
    conn, uow = setup(tmp_path)
    result = set_block(uow)

    assert isinstance(result, Success)
    assert result.value.status == 200
    assert result.value.data == {
        "account_id": "acct-a",
        "restriction": "outgoing_blocked",
    }
    assert restriction_of(conn, "acct-a") == ("outgoing_blocked", "dec-r1")
    assert balance(conn, "acct-a") == 1000  # no balance effect
    trace = conn.execute(
        "SELECT operation, external_reference FROM audit_trace WHERE operation = 'risk_restriction'"
    ).fetchall()
    assert trace == [("risk_restriction", "dec-r1")]


def test_clear_removes_the_block_and_its_decision(tmp_path):
    conn, uow = setup(tmp_path)
    set_block(uow)
    result = set_risk_restriction(
        uow,
        clock(),
        RISK,
        "key-r2",
        "acct-a",
        body(action="clear", decision_reference="dec-r2", instruction_id="ins-r2"),
    )

    assert isinstance(result, Success)
    assert result.value.data == {"account_id": "acct-a", "restriction": "none"}
    assert restriction_of(conn, "acct-a") == ("none", None)
    traces = conn.execute(
        "SELECT instruction_id, operation, external_reference FROM audit_trace"
        " WHERE operation = 'risk_restriction' ORDER BY sequence"
    ).fetchall()
    assert traces == [
        ("ins-r1", "risk_restriction", "dec-r1"),
        ("ins-r2", "risk_restriction", "dec-r2"),
    ]


def test_a_state_that_does_not_change_is_refused_without_effect(tmp_path):
    conn, uow = setup(tmp_path)
    before = conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0]

    clear_unset = set_risk_restriction(
        uow, clock(), RISK, "key-c", "acct-a", body(action="clear")
    )
    set_block(uow)
    set_again = set_block(uow, decision="dec-r9", key="key-s", instruction="ins-r9")

    assert isinstance(clear_unset, Failure)
    assert clear_unset.error.code == "INVALID_TRANSITION"
    assert isinstance(set_again, Failure)
    assert set_again.error.code == "INVALID_TRANSITION"
    assert restriction_of(conn, "acct-a") == ("outgoing_blocked", "dec-r1")
    assert conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0] == before + 1


def test_exact_replay_returns_the_stored_result_without_a_second_trace(tmp_path):
    conn, uow = setup(tmp_path)
    first = set_block(uow)
    traces = conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0]
    replay = set_block(uow)

    assert isinstance(replay, Success)
    assert replay.replayed is True
    assert replay.value.data == first.value.data
    assert conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0] == traces


def test_same_key_with_a_different_request_is_a_conflict(tmp_path):
    conn, uow = setup(tmp_path)
    set_block(uow)
    result = set_block(uow, decision="dec-other")

    assert isinstance(result, Failure)
    assert result.error.code == "IDEMPOTENCY_CONFLICT"
    assert restriction_of(conn, "acct-a") == ("outgoing_blocked", "dec-r1")


def test_refusals_for_role_account_action_and_body(tmp_path):
    conn, uow = setup(tmp_path)
    wrong_role = set_risk_restriction(uow, clock(), PAYER, "k1", "acct-a", body())
    unknown = set_risk_restriction(uow, clock(), RISK, "k2", "acct-zz", body())
    bad_action = set_risk_restriction(
        uow, clock(), RISK, "k3", "acct-a", body(action="toggle")
    )

    assert wrong_role.error.code == "FORBIDDEN_SCOPE"
    assert unknown.error.code == "ACCOUNT_NOT_FOUND"
    assert bad_action.error.code == "VALIDATION_ERROR"
    assert restriction_of(conn, "acct-a") == ("none", None)


def test_block_refuses_outgoing_activity_and_permits_the_rest(tmp_path):
    conn, uow = setup(tmp_path)
    set_block(uow)
    now = clock()

    # refused by the block: outgoing ACH, internal transfer, card authorization
    outgoing = create_outgoing_ach(
        uow,
        now,
        PAYER,
        "k-out",
        "acct-a",
        {
            "instruction_id": "ins-o",
            "movement_id": "mv-o",
            "amount_cents": 100,
            "currency": "USD",
            "external_reference": "ext-o",
            "destination_reference": "dest-1",
        },
    )
    transfer = internal_transfer(
        uow,
        now,
        PAYER,
        "k-tr",
        {
            "instruction_id": "ins-t",
            "movement_id": "mv-t",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": 100,
            "currency": "USD",
        },
    )
    card = authorize_card(
        uow,
        now,
        CARD,
        "k-card",
        "acct-a",
        {
            "instruction_id": "ins-c",
            "movement_id": "mv-c",
            "amount_cents": 100,
            "currency": "USD",
            "external_reference": "ext-c",
            "merchant_reference": "m-1",
        },
    )
    for result in (outgoing, transfer, card):
        assert isinstance(result, Failure)
        assert result.error.code == "OUTGOING_BLOCKED"

    # permitted: incoming credit (notice and settlement)
    notice = create_incoming_ach(
        uow,
        now,
        PAYER,
        "k-in",
        "acct-a",
        {
            "instruction_id": "ins-i",
            "movement_id": "mv-i",
            "amount_cents": 250,
            "currency": "USD",
            "external_reference": "ext-i",
        },
    )
    settled = settle_incoming_ach(
        uow,
        now,
        PAYER,
        "k-in-s",
        "acct-a",
        "mv-i",
        {"instruction_id": "ins-is", "evidence_reference": "ev-i"},
    )
    assert isinstance(notice, Success) and isinstance(settled, Success)
    assert balance(conn, "acct-a") == 1250

    # permitted: reads
    read = get_account(uow, READER, "acct-a")
    assert isinstance(read, Success)
    assert read.value.data["restriction"] == "outgoing_blocked"

    # permitted: approved correction
    correction = create_correction(
        uow,
        now,
        CORRECTOR,
        "k-corr",
        "acct-a",
        {
            "instruction_id": "ins-cc",
            "correction_id": "cor-r",
            "direction": "credit",
            "amount_cents": 50,
            "currency": "USD",
            "decision_reference": "dec-corr",
        },
    )
    assert isinstance(correction, Success)
    assert balance(conn, "acct-a") == 1300


def test_clearing_the_block_allows_outgoing_again(tmp_path):
    conn, uow = setup(tmp_path)
    set_block(uow)
    set_risk_restriction(
        uow,
        clock(),
        RISK,
        "key-r2",
        "acct-a",
        body(action="clear", decision_reference="dec-r2", instruction_id="ins-r2"),
    )
    transfer = internal_transfer(
        uow,
        clock(),
        PAYER,
        "k-tr",
        {
            "instruction_id": "ins-t",
            "movement_id": "mv-t",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": 100,
            "currency": "USD",
        },
    )
    assert isinstance(transfer, Success)
    assert balance(conn, "acct-a") == 900
