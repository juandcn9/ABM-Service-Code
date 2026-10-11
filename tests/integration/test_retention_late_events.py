"""Outgoing return, correction, late card clearing, and refund advance retention (DEC-0046, TEST-19).

The incoming-return case is exercised in test_retention.py.
"""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

from abm.application.caller import CallerContext
from abm.application.cards import authorize_card, clear_card, refund_card, reverse_card
from abm.application.closure import close_account
from abm.application.corrections import create_correction
from abm.application.outgoing_ach import (
    create_outgoing_ach,
    return_outgoing_ach,
    settle_outgoing_ach,
    submit_outgoing_ach,
)
from abm.application.transfers import internal_transfer
from abm.domain.results import Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import fund, open_started, register

REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")
CORRECTOR = CallerContext("corr-1", "correction_authority", "corr-x")
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


def drain(uow, clock: ControllableClock, cents: int) -> None:
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
            "amount_cents": cents,
            "currency": "USD",
        },
    )
    assert isinstance(result, Success)


def close(uow, clock: ControllableClock) -> None:
    result = close_account(
        uow, clock, REGISTRAR, "k-close", "acct-a", {"instruction_id": "ins-close"}
    )
    assert isinstance(result, Success)


def dates(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    return conn.execute(
        "SELECT final_at, eligible_after FROM retention_metadata WHERE account_id = 'acct-a'"
    ).fetchone()


def test_a_late_outgoing_return_advances_the_dates(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    create_outgoing_ach(
        uow,
        clock,
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
    evidence = {"instruction_id": "ins-sub", "evidence_reference": "ev-sub"}
    assert isinstance(
        submit_outgoing_ach(uow, clock, PAYER, "k-sub", "acct-a", "mv-out", evidence),
        Success,
    )
    settled = {"instruction_id": "ins-set", "evidence_reference": "ev-set"}
    assert isinstance(
        settle_outgoing_ach(uow, clock, PAYER, "k-set", "acct-a", "mv-out", settled),
        Success,
    )
    drain(uow, clock, 600)
    close(uow, clock)
    assert dates(conn) == (T0, T7)

    clock.advance(365 * 24 * 3600)
    back = return_outgoing_ach(
        uow,
        clock,
        PAYER,
        "k-back",
        "acct-a",
        "mv-out",
        {
            "instruction_id": "ins-back",
            "evidence_reference": "ev-back",
            "amount_cents": 400,
            "currency": "USD",
        },
    )
    assert isinstance(back, Success)
    assert dates(conn) == ("2027-10-10T12:00:00Z", "2034-10-10T12:00:00Z")


def test_a_late_correction_advances_the_dates(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    drain(uow, clock, 1000)
    close(uow, clock)

    clock.advance(60)
    corrected = create_correction(
        uow,
        clock,
        CORRECTOR,
        "k-corr",
        "acct-a",
        {
            "instruction_id": "ins-corr",
            "correction_id": "cor-late",
            "direction": "credit",
            "amount_cents": 50,
            "currency": "USD",
            "decision_reference": "dec-late",
        },
    )
    assert isinstance(corrected, Success)
    assert dates(conn) == ("2026-10-10T12:01:00Z", "2033-10-10T12:01:00Z")


def test_a_late_card_clearing_and_refund_advance_the_dates(tmp_path):
    clock = ControllableClock(START)
    conn, uow = setup(tmp_path, clock)
    authorize_card(
        uow,
        clock,
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
        clock,
        CARD,
        "k-rev",
        "acct-a",
        "mv-late",
        {"instruction_id": "ins-rev", "evidence_reference": "ev-rev"},
    )
    drain(uow, clock, 1000)
    close(uow, clock)

    clock.advance(60)
    late = clear_card(
        uow,
        clock,
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
    assert dates(conn) == ("2026-10-10T12:01:00Z", "2033-10-10T12:01:00Z")

    clock.advance(60)
    refund = refund_card(
        uow,
        clock,
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
    assert dates(conn) == ("2026-10-10T12:02:00Z", "2033-10-10T12:02:00Z")
