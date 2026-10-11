"""Model-based lifecycle check: seeded random command sequences, invariants after every step (TASK-24, TEST-12, TEST-13, NFR-06)."""

from __future__ import annotations

import pathlib
import random
import sqlite3
from datetime import UTC, datetime
from typing import Any

import pytest

from abm.application.caller import CallerContext
from abm.application.cards import authorize_card, clear_card, reverse_card
from abm.application.closure import close_account
from abm.application.corrections import create_correction
from abm.application.incoming_ach import create_incoming_ach, settle_incoming_ach
from abm.application.outgoing_ach import (
    cancel_outgoing_ach,
    create_outgoing_ach,
    reject_outgoing_ach,
    return_outgoing_ach,
    settle_outgoing_ach,
    submit_outgoing_ach,
)
from abm.application.reads import get_history, get_trace
from abm.application.risk import set_risk_restriction
from abm.application.transfers import internal_transfer
from abm.domain.results import Success
from abm.persistence.readiness import readiness_reasons
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import MIGRATIONS, open_started, register


def payload(result: object) -> dict[str, Any]:
    """The success data of a read, typed for the assertions in this module."""
    assert isinstance(result, Success)
    return dict(result.value.data)


PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")
RISK = CallerContext("risk-1", "risk_controller", "corr-r")
CORRECTOR = CallerContext("corr-1", "correction_authority", "corr-x")
REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
RECON = CallerContext("recon-1", "reconciliation_reader", "corr-t")
ACCOUNTS = ("acct-a", "acct-b")
STEPS = 400


def reader(account: str) -> CallerContext:
    return CallerContext(
        f"rd-{account}", "account_reader", "corr-d", account_scope=account
    )


def check_invariants(
    conn: sqlite3.Connection, uow: SqliteUnitOfWork, recon_seen: list[int]
) -> None:
    # 1. stored balance equals the signed sum of the ledger (INV-07, INV-10)
    sums = dict(
        conn.execute(
            "SELECT account_id, SUM(CASE direction WHEN 'credit' THEN amount_cents"
            " ELSE -amount_cents END) FROM ledger_entries GROUP BY account_id"
        ).fetchall()
    )
    for account, balance in conn.execute(
        "SELECT account_id, current_balance_cents FROM accounts"
    ):
        assert balance == sums.get(account, 0), account

    # 2. history walks return every ledger row of the account, once, in order (NFR-06)
    for account in ACCOUNTS:
        expected = conn.execute(
            "SELECT COUNT(*) FROM ledger_entries WHERE account_id = ?", (account,)
        ).fetchone()[0]
        seen: list[int] = []
        cursor = 0
        while True:
            page = get_history(uow, reader(account), account, cursor, 3)
            assert isinstance(page, Success)
            seen += [item["sequence"] for item in payload(page)["items"]]
            cursor = payload(page)["next_after_sequence"]
            if cursor is None:
                break
        assert len(seen) == expected == len(set(seen)) and seen == sorted(seen), account

    # 3. the reconciliation trace is complete, ordered and gap-free through its cutoff (TEST-12)
    trace_total = conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0]
    walked: list[int] = []
    cursor = 0
    cutoff = None
    while True:
        page = get_trace(uow, RECON, cursor, 4, cutoff)
        assert isinstance(page, Success)
        cutoff = payload(page)["cutoff_sequence"]
        walked += [item["sequence"] for item in payload(page)["items"]]
        cursor = payload(page)["next_after_sequence"]
        if cursor is None:
            break
    assert walked == sorted(set(walked)) and len(walked) == trace_total
    recon_seen[:] = walked

    # 4. readiness stays clean after every committed step (INV-18)
    assert readiness_reasons(conn, MIGRATIONS) == []


def act(
    rng: random.Random,
    conn: sqlite3.Connection,
    uow: SqliteUnitOfWork,
    now: ControllableClock,
    n: int,
) -> str:
    a = rng.choice(ACCOUNTS)
    b = "acct-b" if a == "acct-a" else "acct-a"
    # closure is rare so that most steps exercise open accounts; the others are weighted
    if rng.random() < 1 / 60:
        kind = "close"
    else:
        kind = rng.choice(
            ["incoming"] * 3
            + ["settle"] * 3
            + ["transfer"] * 3
            + ["card"] * 2
            + ["reverse", "clear", "clear", "correct", "risk"]
            + ["out_create"] * 3
            + [
                "out_submit",
                "out_settle",
                "out_settle",
                "out_reject",
                "out_cancel",
                "out_return",
            ]
        )
    cents = rng.randint(1, 300)
    mv = f"mv-{n}"
    if kind == "incoming":
        create_incoming_ach(
            uow,
            now,
            PAYER,
            f"k-{n}",
            a,
            {
                "instruction_id": f"ins-{n}",
                "movement_id": mv,
                "amount_cents": cents,
                "currency": "USD",
                "external_reference": f"ext-{n}",
            },
        )
    elif kind == "settle":
        # the most recent incoming movement of this account, if any (may be refused)
        row = last_movement(conn, a, "incoming_ach")
        if row:
            settle_incoming_ach(
                uow,
                now,
                PAYER,
                f"k-{n}",
                a,
                row,
                {"instruction_id": f"ins-{n}", "evidence_reference": f"ev-{n}"},
            )
    elif kind == "transfer":
        internal_transfer(
            uow,
            now,
            PAYER,
            f"k-{n}",
            {
                "instruction_id": f"ins-{n}",
                "movement_id": mv,
                "source_account_id": a,
                "destination_account_id": b,
                "amount_cents": cents,
                "currency": "USD",
            },
        )
    elif kind == "card":
        authorize_card(
            uow,
            now,
            CARD,
            f"k-{n}",
            a,
            {
                "instruction_id": f"ins-{n}",
                "movement_id": mv,
                "amount_cents": cents,
                "currency": "USD",
                "external_reference": f"ext-{n}",
                "merchant_reference": "m-1",
            },
        )
    elif kind == "reverse":
        row = last_movement(conn, a, "card")
        if row:
            reverse_card(
                uow,
                now,
                CARD,
                f"k-{n}",
                a,
                row,
                {"instruction_id": f"ins-{n}", "evidence_reference": f"ev-{n}"},
            )
    elif kind == "clear":
        row = last_movement(conn, a, "card")
        if row:
            clear_card(
                uow,
                now,
                CARD,
                f"k-{n}",
                a,
                row,
                {
                    "instruction_id": f"ins-{n}",
                    "evidence_reference": f"ev-{n}",
                    "amount_cents": cents,
                    "currency": "USD",
                },
            )
    elif kind == "correct":
        create_correction(
            uow,
            now,
            CORRECTOR,
            f"k-{n}",
            a,
            {
                "instruction_id": f"ins-{n}",
                "correction_id": f"cor-{n}",
                "direction": rng.choice(["credit", "debit"]),
                "amount_cents": cents,
                "currency": "USD",
                "decision_reference": f"dec-{n}",
            },
        )
    elif kind == "risk":
        set_risk_restriction(
            uow,
            now,
            RISK,
            f"k-{n}",
            a,
            {
                "instruction_id": f"ins-{n}",
                "action": rng.choice(["set", "clear"]),
                "decision_reference": f"dec-{n}",
            },
        )
    elif kind == "out_create":
        create_outgoing_ach(
            uow,
            now,
            PAYER,
            f"k-{n}",
            a,
            {
                "instruction_id": f"ins-{n}",
                "movement_id": f"mo-{n}",
                "amount_cents": cents,
                "currency": "USD",
                "external_reference": f"ext-{n}",
                "destination_reference": "dest-1",
            },
        )
    elif kind in ("out_submit", "out_settle", "out_reject", "out_cancel"):
        required = {
            "out_submit": "accepted_with_hold",
            "out_cancel": "accepted_with_hold",
            "out_settle": "submitted",
            "out_reject": "submitted",
        }[kind]
        row = last_movement(conn, a, "outgoing_ach", required)
        if row:
            command = {
                "out_submit": submit_outgoing_ach,
                "out_settle": settle_outgoing_ach,
                "out_reject": reject_outgoing_ach,
                "out_cancel": cancel_outgoing_ach,
            }[kind]
            command(
                uow,
                now,
                PAYER,
                f"k-{n}",
                a,
                row,
                {"instruction_id": f"ins-{n}", "evidence_reference": f"ev-{n}"},
            )
    elif kind == "out_return":
        row = last_movement(conn, a, "outgoing_ach", "settled")
        if row:
            amount = conn.execute(
                "SELECT amount_cents FROM movements WHERE movement_id = ?", (row,)
            ).fetchone()[0]
            return_outgoing_ach(
                uow,
                now,
                PAYER,
                f"k-{n}",
                a,
                row,
                {
                    "instruction_id": f"ins-{n}",
                    "evidence_reference": f"ev-{n}",
                    "amount_cents": amount,
                    "currency": "USD",
                },
            )
    else:
        close_account(uow, now, REGISTRAR, f"k-{n}", a, {"instruction_id": f"ins-{n}"})

    return kind


def step(
    rng: random.Random,
    conn: sqlite3.Connection,
    uow: SqliteUnitOfWork,
    now: ControllableClock,
    n: int,
) -> tuple[str, bool]:
    """One random command; returns its kind and whether it was accepted (a new trace row was written)."""
    before = conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0]
    kind = act(rng, conn, uow, now, n)
    after = conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0]
    return kind, after > before


def last_movement(
    conn: sqlite3.Connection, account: str, movement_type: str, state: str | None = None
) -> str | None:
    """Test helper: the newest movement of one type (and state, if given) for an account."""
    sql = (
        "SELECT movement_id FROM movements WHERE account_id = ? AND movement_type = ?"
        + (" AND state = ?" if state is not None else "")
        + " ORDER BY created_at DESC, movement_id DESC LIMIT 1"
    )
    args: tuple[object, ...] = (account, movement_type) + (
        (state,) if state is not None else ()
    )
    row = conn.execute(sql, args).fetchone()
    return None if row is None else row[0]


def run_sequence(tmp_path: pathlib.Path, seed: int) -> tuple[list[int], dict[str, int]]:
    """Run one seeded sequence, checking every invariant after every step; return the trace and accepted kinds."""
    conn = open_started(tmp_path / f"model-{seed}.sqlite3")
    uow = SqliteUnitOfWork(conn)
    now = ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
    for account in ACCOUNTS:
        register(uow, now, account)
    rng = random.Random(seed)
    recon_seen: list[int] = []
    accepted_kinds: dict[str, int] = {}
    for n in range(STEPS):
        now.advance(1)
        kind, accepted = step(rng, conn, uow, now, n)
        if accepted:
            accepted_kinds[kind] = accepted_kinds.get(kind, 0) + 1
        check_invariants(conn, uow, recon_seen)
    conn.close()
    return recon_seen, accepted_kinds


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_random_lifecycles_keep_every_invariant_at_every_step(
    tmp_path: pathlib.Path, seed: int
):
    recon_seen, accepted_kinds = run_sequence(tmp_path, seed)
    assert len(recon_seen) >= 100  # the sequence must do real work, not just be refused
    # every command family is accepted at least once in each seed (measured: all but reject)
    for kind in (
        "incoming",
        "settle",
        "transfer",
        "correct",
        "risk",
        "card",
        "reverse",
        "clear",
        "out_create",
        "out_submit",
        "out_settle",
        "out_cancel",
        "out_return",
    ):
        assert accepted_kinds.get(kind, 0) >= 1, (kind, accepted_kinds)


def test_outgoing_rejection_is_accepted_across_the_seeds(
    tmp_path: pathlib.Path,
):
    """Rejection is rarer than the other commands; checked over the fixed seeds together."""
    totals: dict[str, int] = {}
    for seed in (1, 2, 3, 4, 5):
        _, accepted = run_sequence(tmp_path, seed)
        for kind, count in accepted.items():
            totals[kind] = totals.get(kind, 0) + count
    for kind in (
        "out_settle",
        "out_return",
        "out_reject",
        "out_cancel",
        "card",
        "reverse",
        "clear",
        "risk",
    ):
        assert totals.get(kind, 0) >= 1, (kind, totals)
