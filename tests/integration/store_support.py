"""Shared fixtures-as-functions for the TASK-18 concurrency and fault-injection tests (not collected by pytest)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

from abm.application.caller import CallerContext
from abm.application.incoming_ach import create_incoming_ach, settle_incoming_ach
from abm.application.outgoing_ach import (
    create_outgoing_ach,
    settle_outgoing_ach,
    submit_outgoing_ach,
)
from abm.application.registration import register_account
from abm.domain.results import Success
from abm.persistence.migrations import load_migrations
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = load_migrations(ROOT / "migrations")
NOW = "2026-10-10T12:00:00Z"
REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")


def clock() -> ControllableClock:
    return ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))


def open_started(path: pathlib.Path) -> sqlite3.Connection:
    started = start_database(path, MIGRATIONS, NOW)
    assert started.ready, started.reasons
    assert started.connection is not None
    return started.connection


def register(uow: SqliteUnitOfWork, now: ControllableClock, account: str) -> None:
    body = {
        "instruction_id": f"ins-reg-{account}",
        "account_id": account,
        "customer_id": f"cust-{account}",
        "currency": "USD",
        "eligibility_reference": "elig-1",
    }
    assert isinstance(
        register_account(uow, now, REGISTRAR, f"key-reg-{account}", body), Success
    )


def fund(
    uow: SqliteUnitOfWork, now: ControllableClock, account: str, cents: int
) -> None:
    movement = f"mv-in-{account}"
    notice = {
        "instruction_id": f"ins-n-{account}",
        "movement_id": movement,
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": f"ext-{account}",
    }
    assert isinstance(
        create_incoming_ach(uow, now, PAYER, f"kn-{account}", account, notice), Success
    )
    settled = {
        "instruction_id": f"ins-s-{account}",
        "evidence_reference": f"ev-{account}",
    }
    assert isinstance(
        settle_incoming_ach(
            uow, now, PAYER, f"ks-{account}", account, movement, settled
        ),
        Success,
    )


def setup_funded(path: pathlib.Path) -> None:
    """acct-a holds 1000 cents of available funds; acct-b is an open destination."""
    conn = open_started(path)
    uow, now = SqliteUnitOfWork(conn), clock()
    register(uow, now, "acct-a")
    register(uow, now, "acct-b")
    fund(uow, now, "acct-a", 1000)
    conn.close()


def setup_submitted(path: pathlib.Path) -> None:
    """Funded acct-a, and outgoing movement mv-o (400 cents) accepted with a hold, then submitted."""
    setup_funded(path)
    conn = open_started(path)
    uow, now = SqliteUnitOfWork(conn), clock()
    body = {
        "instruction_id": "ins-o",
        "movement_id": "mv-o",
        "amount_cents": 400,
        "currency": "USD",
        "external_reference": "ext-o",
        "destination_reference": "dest-o",
    }
    assert isinstance(
        create_outgoing_ach(uow, now, PAYER, "ko", "acct-a", body), Success
    )
    evidence = {"instruction_id": "ins-sub", "evidence_reference": "ev-sub"}
    assert isinstance(
        submit_outgoing_ach(uow, now, PAYER, "ksub", "acct-a", "mv-o", evidence),
        Success,
    )
    conn.close()


def setup_settled(path: pathlib.Path) -> None:
    setup_submitted(path)
    conn = open_started(path)
    uow, now = SqliteUnitOfWork(conn), clock()
    evidence = {"instruction_id": "ins-st", "evidence_reference": "ev-st"}
    assert isinstance(
        settle_outgoing_ach(uow, now, PAYER, "kst", "acct-a", "mv-o", evidence),
        Success,
    )
    conn.close()


def snapshot(conn: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    """Every row of every application table, sorted, so two snapshots compare as values."""
    names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return {
        name: sorted(conn.execute(f"SELECT * FROM {name}").fetchall(), key=repr)
        for name in names
    }
