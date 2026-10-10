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
from abm.application.cards import clear_card, expire_card, refund_card, reverse_card
from abm.application.incoming_ach import (
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
    fund(uow, now, "acct-b", 1000)
    # an outgoing movement and an incoming settlement that belong to acct-b
    body = {
        "instruction_id": "ins-out",
        "movement_id": "mv-out-b",
        "amount_cents": 400,
        "currency": "USD",
        "external_reference": "ext-out-b",
        "destination_reference": "dest-1",
    }
    assert isinstance(
        create_outgoing_ach(uow, now, PAYER, "k-out", "acct-b", body), Success
    )
    assert isinstance(
        submit_outgoing_ach(
            uow,
            now,
            PAYER,
            "k-sub",
            "acct-b",
            "mv-out-b",
            {"instruction_id": "ins-sub", "evidence_reference": "ev-sub"},
        ),
        Success,
    )
    return conn, uow, now


def _attempts(uow, now, account: str, movement: str, tag: str):
    """Each movement-bearing command, called with `account` and `movement`, under one fresh key each."""
    ev = {"instruction_id": f"ins-{tag}", "evidence_reference": f"ev-{tag}"}
    give_back = {
        "instruction_id": f"ins-r-{tag}",
        "evidence_reference": f"ev-r-{tag}",
        "amount_cents": 400,
        "currency": "USD",
    }
    return {
        "settle_outgoing": settle_outgoing_ach(
            uow, now, PAYER, f"k-so-{tag}", account, movement, ev
        ),
        "reject_outgoing": reject_outgoing_ach(
            uow, now, PAYER, f"k-xo-{tag}", account, movement, ev
        ),
        "cancel_outgoing": cancel_outgoing_ach(
            uow, now, PAYER, f"k-co-{tag}", account, movement, ev
        ),
        "return_outgoing": return_outgoing_ach(
            uow, now, PAYER, f"k-ro-{tag}", account, movement, give_back
        ),
        "settle_incoming": settle_incoming_ach(
            uow, now, PAYER, f"k-si-{tag}", account, movement, ev
        ),
        "return_incoming": return_incoming_ach(
            uow, now, PAYER, f"k-ri-{tag}", account, movement, give_back
        ),
        "card_reverse": reverse_card(
            uow, now, CARD, f"k-cr-{tag}", account, movement, ev
        ),
        "card_expire": expire_card(
            uow, now, CARD, f"k-ce-{tag}", account, movement, ev
        ),
        "card_clear": clear_card(
            uow,
            now,
            CARD,
            f"k-cc-{tag}",
            account,
            movement,
            {**ev, "amount_cents": 400, "currency": "USD"},
        ),
        "card_refund": refund_card(
            uow,
            now,
            CARD,
            f"k-cf-{tag}",
            account,
            movement,
            {**ev, "amount_cents": 400, "currency": "USD"},
        ),
    }


def test_a_movement_of_another_account_is_refused_exactly_like_a_missing_one(setup_two):
    """TEST-23: no existence leak and no write when a path account names someone else's movement."""
    conn, uow, now = setup_two
    before = (
        conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone(),
        conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone(),
        conn.execute("SELECT COUNT(*) FROM movements").fetchone(),
    )
    foreign = _attempts(uow, now, "acct-a", "mv-out-b", "x")
    missing = _attempts(uow, now, "acct-a", "mv-nope", "y")

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
    )
    assert after == before
