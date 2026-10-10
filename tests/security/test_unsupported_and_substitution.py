"""Unsupported operations do not exist; a movement from another account is refused like a missing one (TEST-20, TEST-23)."""

from __future__ import annotations

import importlib
import inspect
import pathlib
import pkgutil
import sqlite3

import pytest

import abm.application as application_pkg
from abm.application.caller import CallerContext
from abm.application.cards import (
    authorize_card,
    clear_card,
    expire_card,
    refund_card,
    reverse_card,
)
from abm.application.incoming_ach import (
    create_incoming_ach,
    return_incoming_ach,
    settle_incoming_ach,
)
from abm.application.outgoing_ach import (
    cancel_outgoing_ach,
    create_outgoing_ach,
    reject_outgoing_ach,
    return_outgoing_ach,
    settle_outgoing_ach,
    submit_outgoing_ach,
)
from abm.domain.results import Failure, Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import clock, fund, open_started, register

PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")
UNSUPPORTED_VERBS = (
    "delete",
    "remove",
    "update",
    "edit",
    "reopen",
    "replace",
    "set_balance",
    "adjust",
)


def test_no_application_operation_updates_deletes_or_reopens(tmp_path):
    """TEST-20: the excluded operations have no implementation to call."""
    found = []
    for module_info in pkgutil.iter_modules(application_pkg.__path__):
        module = importlib.import_module(f"abm.application.{module_info.name}")
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if obj.__module__ != module.__name__ or name.startswith("_"):
                continue
            if any(name.startswith(verb) for verb in UNSUPPORTED_VERBS):
                found.append(f"{module_info.name}.{name}")
    assert found == []


@pytest.fixture
def setup_two(tmp_path: pathlib.Path):
    conn: sqlite3.Connection = open_started(tmp_path / "abm.sqlite3")
    uow = SqliteUnitOfWork(conn)
    now: ControllableClock = clock()
    register(uow, now, "acct-a")
    register(uow, now, "acct-b")
    fund(uow, now, "acct-b", 5000)

    def outgoing(movement: str, amount: int, suffix: str) -> None:
        assert isinstance(
            create_outgoing_ach(
                uow,
                now,
                PAYER,
                f"k-out-{suffix}",
                "acct-b",
                {
                    "instruction_id": f"ins-out-{suffix}",
                    "movement_id": movement,
                    "amount_cents": amount,
                    "currency": "USD",
                    "external_reference": f"ext-out-{suffix}",
                    "destination_reference": "dest-1",
                },
            ),
            Success,
        )

    outgoing("mv-out-submitted", 400, "submitted")
    assert isinstance(
        submit_outgoing_ach(
            uow,
            now,
            PAYER,
            "k-submitted",
            "acct-b",
            "mv-out-submitted",
            {"instruction_id": "ins-submitted", "evidence_reference": "ev-submitted"},
        ),
        Success,
    )
    outgoing("mv-out-accepted", 300, "accepted")
    outgoing("mv-out-return", 200, "return")
    assert isinstance(
        submit_outgoing_ach(
            uow,
            now,
            PAYER,
            "k-return-sub",
            "acct-b",
            "mv-out-return",
            {"instruction_id": "ins-return-sub", "evidence_reference": "ev-return-sub"},
        ),
        Success,
    )
    assert isinstance(
        settle_outgoing_ach(
            uow,
            now,
            PAYER,
            "k-return-settle",
            "acct-b",
            "mv-out-return",
            {
                "instruction_id": "ins-return-settle",
                "evidence_reference": "ev-return-settle",
            },
        ),
        Success,
    )

    def incoming(movement: str, amount: int, suffix: str) -> None:
        assert isinstance(
            create_incoming_ach(
                uow,
                now,
                PAYER,
                f"k-in-{suffix}",
                "acct-b",
                {
                    "instruction_id": f"ins-in-{suffix}",
                    "movement_id": movement,
                    "amount_cents": amount,
                    "currency": "USD",
                    "external_reference": f"ext-in-{suffix}",
                },
            ),
            Success,
        )

    incoming("mv-in-pending", 100, "pending")
    incoming("mv-in-return", 150, "return")
    assert isinstance(
        settle_incoming_ach(
            uow,
            now,
            PAYER,
            "k-in-settle",
            "acct-b",
            "mv-in-return",
            {"instruction_id": "ins-in-settle", "evidence_reference": "ev-in-settle"},
        ),
        Success,
    )

    def card(movement: str, amount: int, suffix: str) -> None:
        assert isinstance(
            authorize_card(
                uow,
                now,
                CARD,
                f"k-card-{suffix}",
                "acct-b",
                {
                    "instruction_id": f"ins-card-{suffix}",
                    "movement_id": movement,
                    "amount_cents": amount,
                    "currency": "USD",
                    "external_reference": f"ext-card-{suffix}",
                    "merchant_reference": "merchant-1",
                },
            ),
            Success,
        )

    card("mv-card-auth", 100, "auth")
    card("mv-card-refund", 120, "refund")
    assert isinstance(
        clear_card(
            uow,
            now,
            CARD,
            "k-card-clear",
            "acct-b",
            "mv-card-refund",
            {
                "instruction_id": "ins-card-clear",
                "evidence_reference": "ev-card-clear",
                "amount_cents": 120,
                "currency": "USD",
            },
        ),
        Success,
    )
    movements = {
        "submit_outgoing": "mv-out-accepted",
        "settle_outgoing": "mv-out-submitted",
        "reject_outgoing": "mv-out-submitted",
        "cancel_outgoing": "mv-out-accepted",
        "return_outgoing": "mv-out-return",
        "settle_incoming": "mv-in-pending",
        "return_incoming": "mv-in-return",
        "card_reverse": "mv-card-auth",
        "card_expire": "mv-card-auth",
        "card_clear": "mv-card-auth",
        "card_refund": "mv-card-refund",
    }
    return conn, uow, now, movements


def _attempts(uow, now, account: str, movements: dict[str, str], tag: str):
    """Every movement-bearing command, each given its own relevant-state movement."""
    ev = {"instruction_id": f"ins-{tag}", "evidence_reference": f"ev-{tag}"}
    give_back = {
        "instruction_id": f"ins-r-{tag}",
        "evidence_reference": f"ev-r-{tag}",
        "amount_cents": 400,
        "currency": "USD",
    }
    return {
        "submit_outgoing": submit_outgoing_ach(
            uow, now, PAYER, f"k-su-{tag}", account, movements["submit_outgoing"], ev
        ),
        "settle_outgoing": settle_outgoing_ach(
            uow, now, PAYER, f"k-so-{tag}", account, movements["settle_outgoing"], ev
        ),
        "reject_outgoing": reject_outgoing_ach(
            uow, now, PAYER, f"k-xo-{tag}", account, movements["reject_outgoing"], ev
        ),
        "cancel_outgoing": cancel_outgoing_ach(
            uow, now, PAYER, f"k-co-{tag}", account, movements["cancel_outgoing"], ev
        ),
        "return_outgoing": return_outgoing_ach(
            uow,
            now,
            PAYER,
            f"k-ro-{tag}",
            account,
            movements["return_outgoing"],
            give_back,
        ),
        "settle_incoming": settle_incoming_ach(
            uow, now, PAYER, f"k-si-{tag}", account, movements["settle_incoming"], ev
        ),
        "return_incoming": return_incoming_ach(
            uow,
            now,
            PAYER,
            f"k-ri-{tag}",
            account,
            movements["return_incoming"],
            give_back,
        ),
        "card_reverse": reverse_card(
            uow, now, CARD, f"k-cr-{tag}", account, movements["card_reverse"], ev
        ),
        "card_expire": expire_card(
            uow, now, CARD, f"k-ce-{tag}", account, movements["card_expire"], ev
        ),
        "card_clear": clear_card(
            uow,
            now,
            CARD,
            f"k-cc-{tag}",
            account,
            movements["card_clear"],
            {**ev, "amount_cents": 400, "currency": "USD"},
        ),
        "card_refund": refund_card(
            uow,
            now,
            CARD,
            f"k-cf-{tag}",
            account,
            movements["card_refund"],
            {**ev, "amount_cents": 400, "currency": "USD"},
        ),
    }


def test_a_movement_of_another_account_is_refused_exactly_like_a_missing_one(setup_two):
    """TEST-23: no existence leak or business mutation; required 404 outcomes are stored."""
    conn, uow, now, movements = setup_two
    before = (
        conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone(),
        conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone(),
        conn.execute("SELECT COUNT(*) FROM movements").fetchone(),
        conn.execute("SELECT COUNT(*) FROM holds").fetchone(),
        conn.execute("SELECT COUNT(*) FROM movement_evidence").fetchone(),
        conn.execute(
            "SELECT account_id, current_balance_cents, restriction FROM accounts ORDER BY account_id"
        ).fetchall(),
    )
    outcomes_before = conn.execute(
        "SELECT COUNT(*) FROM idempotency_outcomes"
    ).fetchone()[0]
    foreign = _attempts(uow, now, "acct-a", movements, "x")
    missing = _attempts(
        uow,
        now,
        "acct-a",
        {name: f"mv-nope-{name}" for name in movements},
        "y",
    )

    for name in foreign:
        a, b = foreign[name], missing[name]
        assert isinstance(a, Failure) and isinstance(b, Failure), name
        assert (a.error.code, a.error.safe_message) == (
            b.error.code,
            b.error.safe_message,
        ), name
    after = (
        conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone(),
        conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone(),
        conn.execute("SELECT COUNT(*) FROM movements").fetchone(),
        conn.execute("SELECT COUNT(*) FROM holds").fetchone(),
        conn.execute("SELECT COUNT(*) FROM movement_evidence").fetchone(),
        conn.execute(
            "SELECT account_id, current_balance_cents, restriction FROM accounts ORDER BY account_id"
        ).fetchall(),
    )
    assert after == before
    outcomes_after = conn.execute(
        "SELECT COUNT(*) FROM idempotency_outcomes"
    ).fetchone()[0]
    assert outcomes_after == outcomes_before + 2 * len(foreign)
