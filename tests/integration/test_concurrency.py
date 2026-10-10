"""Concurrency barriers: independent connections race for the same funds or movement (TEST-14, specs/08 section 6).

Each contender opens its own connection, reads the same initial state, waits at a barrier, and only then
attempts BEGIN IMMEDIATE. Assertions are on outcomes and final state, never on timing or winner order.
"""

from __future__ import annotations

import pathlib
import threading
from collections.abc import Callable
from typing import Any

import pytest

from abm.application.caller import CallerContext
from abm.application.cards import clear_card, refund_card
from abm.application.idempotency import Response
from abm.application.outgoing_ach import (
    create_outgoing_ach,
    reject_outgoing_ach,
    return_outgoing_ach,
    settle_outgoing_ach,
)
from abm.application.transfers import internal_transfer
from abm.domain.results import Failure, Result, Success
from abm.persistence.database import open_database
from abm.persistence.readiness import readiness_reasons
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import (
    MIGRATIONS,
    PAYER,
    clock,
    open_started,
    setup_card_authorized,
    setup_funded,
    setup_settled,
    setup_submitted,
)

REPEATS = 20
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")
EVIDENCE_OF_FINAL_STATE = {
    "settled": "settlement",
    "rejected": "rejection",
    "returned": "return",
}

Contender = Callable[[SqliteUnitOfWork, ControllableClock], Result[Response]]


def race(path: pathlib.Path, contenders: list[Contender]) -> list[Result[Response]]:
    """Run each contender on its own connection. All read the same state, then start together."""
    count = len(contenders)
    barrier = threading.Barrier(count)
    results: list[object] = [None] * count
    now = clock()

    def run(index: int) -> None:
        conn = open_database(path)
        try:
            # every contender observes the same initial balance before any BEGIN IMMEDIATE
            conn.execute(
                "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-a'"
            ).fetchone()
            barrier.wait(timeout=30)
            results[index] = contenders[index](SqliteUnitOfWork(conn), now)
        except BaseException as exc:  # noqa: BLE001  # re-raised in the test thread
            results[index] = exc
        finally:
            conn.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    for value in results:
        if isinstance(value, BaseException):
            raise value
    return list(results)  # type: ignore[arg-type]


def scalar(path: pathlib.Path, sql: str, *params: object) -> Any:
    conn = open_database(path)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def successes(results: list[Result[Response]]) -> list[int]:
    return [i for i, r in enumerate(results) if isinstance(r, Success)]


def transfer(movement: str, key: str, instruction: str) -> Contender:
    body = {
        "instruction_id": instruction,
        "movement_id": movement,
        "source_account_id": "acct-a",
        "destination_account_id": "acct-b",
        "amount_cents": 700,
        "currency": "USD",
    }
    return lambda uow, now: internal_transfer(uow, now, PAYER, key, body)


def outgoing(movement: str, key: str, instruction: str) -> Contender:
    body = {
        "instruction_id": instruction,
        "movement_id": movement,
        "amount_cents": 700,
        "currency": "USD",
        "external_reference": f"ext-{movement}",
        "destination_reference": "dest-x",
    }
    return lambda uow, now: create_outgoing_ach(uow, now, PAYER, key, "acct-a", body)


DEBIT_CASES = {
    "transfer_vs_transfer": (
        setup_funded,
        [transfer("mv-1", "k1", "ins-1"), transfer("mv-2", "k2", "ins-2")],
        ("mv-1", "mv-2"),
    ),
    "transfer_vs_outgoing_hold": (
        setup_funded,
        [transfer("mv-1", "k1", "ins-1"), outgoing("mv-2", "k2", "ins-2")],
        ("mv-1", "mv-2"),
    ),
}


@pytest.mark.parametrize("case", sorted(DEBIT_CASES))
def test_two_debits_against_the_same_available_funds_apply_at_most_one(
    tmp_path: pathlib.Path, case: str
) -> None:
    setup, contenders, movements = DEBIT_CASES[case]
    for repeat in range(REPEATS):
        path = tmp_path / f"{case}-{repeat}.sqlite3"
        setup(path)
        results = race(path, contenders)

        won = successes(results)
        assert len(won) == 1, results
        loser = results[1 - won[0]]
        assert isinstance(loser, Failure) and loser.error.code == "INSUFFICIENT_FUNDS"

        # exactly one effect; available balance is 1000 - 700 and never negative
        applied = scalar(
            path,
            "SELECT COUNT(*) FROM movements WHERE movement_id IN (?, ?)",
            *movements,
        )
        assert applied == 1
        current = scalar(
            path,
            "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-a'",
        )
        held = scalar(
            path,
            "SELECT COALESCE(SUM(amount_cents), 0) FROM holds"
            " WHERE account_id = 'acct-a' AND state = 'active'",
        )
        assert current - held == 300
        assert current - held >= 0

        conn = open_started(path)
        try:
            assert readiness_reasons(conn, MIGRATIONS) == []
        finally:
            conn.close()


def _settle(key: str, evidence: str) -> Contender:
    return lambda uow, now: settle_outgoing_ach(
        uow,
        now,
        PAYER,
        key,
        "acct-a",
        "mv-o",
        {"instruction_id": f"ins-{key}", "evidence_reference": evidence},
    )


def _reject(key: str, evidence: str) -> Contender:
    return lambda uow, now: reject_outgoing_ach(
        uow,
        now,
        PAYER,
        key,
        "acct-a",
        "mv-o",
        {"instruction_id": f"ins-{key}", "evidence_reference": evidence},
    )


def _return(key: str, evidence: str) -> Contender:
    return lambda uow, now: return_outgoing_ach(
        uow,
        now,
        PAYER,
        key,
        "acct-a",
        "mv-o",
        {
            "instruction_id": f"ins-{key}",
            "evidence_reference": evidence,
            "amount_cents": 400,
            "currency": "USD",
        },
    )


@pytest.mark.parametrize(
    ("case", "setup", "contenders", "final_states", "ledger_delta"),
    [
        # two settlements of one submitted movement under different keys and evidence
        (
            "settle_vs_settle",
            setup_submitted,
            [_settle("ka", "ev-a"), _settle("kb", "ev-b")],
            ("settled", "settled"),
            (1, 1),
        ),
        # settlement against rejection: whichever wins is the single final effect
        (
            "settle_vs_reject",
            setup_submitted,
            [_settle("ka", "ev-a"), _reject("kb", "ev-b")],
            ("settled", "rejected"),
            (1, 0),
        ),
        # two returns of one settled movement under different keys and evidence
        (
            "return_vs_return",
            setup_settled,
            [_return("ka", "ev-a"), _return("kb", "ev-b")],
            ("returned", "returned"),
            (1, 1),
        ),
    ],
)
def test_two_contenders_for_one_movement_produce_exactly_one_final_effect(
    tmp_path: pathlib.Path,
    case: str,
    setup: Callable[[pathlib.Path], None],
    contenders: list[Contender],
    final_states: tuple[str, str],
    ledger_delta: tuple[int, int],
) -> None:
    for repeat in range(REPEATS):
        path = tmp_path / f"{case}-{repeat}.sqlite3"
        setup(path)
        ledger_before = scalar(
            path, "SELECT COUNT(*) FROM ledger_entries WHERE movement_id = 'mv-o'"
        )
        trace_before = scalar(
            path, "SELECT COUNT(*) FROM audit_trace WHERE movement_id = 'mv-o'"
        )

        results = race(path, contenders)

        won = successes(results)
        assert len(won) == 1, results
        loser = results[1 - won[0]]
        assert isinstance(loser, Failure) and loser.error.code == "INVALID_TRANSITION"

        # one final state, one trace row for the winning effect, and ledger effects only where money moves
        assert (
            scalar(path, "SELECT state FROM movements WHERE movement_id = 'mv-o'")
            == final_states[won[0]]
        )
        # TEST-36: exactly one evidence row, of the winning kind (UNIQUE per movement and kind)
        assert (
            scalar(
                path,
                "SELECT COUNT(*) FROM movement_evidence WHERE movement_id = 'mv-o' AND evidence_kind = ?",
                EVIDENCE_OF_FINAL_STATE[final_states[won[0]]],
            )
            == 1
        )
        trace_after = scalar(
            path, "SELECT COUNT(*) FROM audit_trace WHERE movement_id = 'mv-o'"
        )
        assert trace_after - trace_before == 1
        ledger_after = scalar(
            path, "SELECT COUNT(*) FROM ledger_entries WHERE movement_id = 'mv-o'"
        )
        assert ledger_after - ledger_before == ledger_delta[won[0]]

        # the refused contender's outcome is stored once as a deterministic rejection
        rejections = scalar(
            path,
            "SELECT COUNT(*) FROM idempotency_outcomes WHERE outcome_class = 'deterministic_rejection'",
        )
        assert rejections == 1


def test_the_same_key_and_body_from_two_connections_applies_once(
    tmp_path: pathlib.Path,
) -> None:
    for repeat in range(REPEATS):
        path = tmp_path / f"same-key-{repeat}.sqlite3"
        setup_submitted(path)
        same = _settle("kshared", "ev-s")

        results = race(path, [same, same])

        assert all(isinstance(r, Success) for r in results), results
        replays = sorted(r.replayed for r in results if isinstance(r, Success))
        assert replays == [False, True]
        assert (
            scalar(
                path, "SELECT COUNT(*) FROM ledger_entries WHERE movement_id = 'mv-o'"
            )
            == 1
        )
        assert (
            scalar(
                path,
                "SELECT COUNT(*) FROM movements WHERE movement_id = 'mv-o' AND state = 'settled'",
            )
            == 1
        )


def _offset(fn: Callable[..., Result[Response]], key: str, evidence: str) -> Contender:
    body = {
        "instruction_id": f"ins-{key}",
        "evidence_reference": evidence,
        "amount_cents": 400,
        "currency": "USD",
    }
    return lambda uow, now: fn(uow, now, CARD, key, "acct-a", "mv-card", body)


def test_clearing_and_refund_of_one_card_movement_keep_at_most_one_effect_of_each_kind(
    tmp_path: pathlib.Path,
) -> None:
    for repeat in range(REPEATS):
        path = tmp_path / f"card-pair-{repeat}.sqlite3"
        setup_card_authorized(path)
        results = race(
            path,
            [_offset(clear_card, "kc1", "ev-c1"), _offset(refund_card, "kc2", "ev-c2")],
        )

        # clearing never waits on a refund, so it always succeeds; a refund succeeds only after clearing commits
        assert isinstance(results[0], Success), results
        refund_ok = isinstance(results[1], Success)
        if not refund_ok:
            assert isinstance(results[1], Failure)
            assert results[1].error.code == "INVALID_TRANSITION"

        assert scalar(
            path, "SELECT state FROM movements WHERE movement_id = 'mv-card'"
        ) == ("refunded" if refund_ok else "cleared")
        for kind, effect, expected in (
            ("clearing", "card_clearing", 1),
            ("refund", "card_refund", int(refund_ok)),
        ):
            assert (
                scalar(
                    path,
                    "SELECT COUNT(*) FROM movement_evidence WHERE movement_id = 'mv-card' AND evidence_kind = ?",
                    kind,
                )
                == expected
            )
            assert (
                scalar(
                    path,
                    "SELECT COUNT(*) FROM ledger_entries WHERE movement_id = 'mv-card' AND effect_kind = ?",
                    effect,
                )
                == expected
            )


def test_settlement_and_return_of_one_movement_keep_at_most_one_effect_of_each_kind(
    tmp_path: pathlib.Path,
) -> None:
    for repeat in range(REPEATS):
        path = tmp_path / f"offset-pair-{repeat}.sqlite3"
        setup_submitted(path)
        results = race(path, [_settle("ka", "ev-a"), _return("kb", "ev-b")])

        # a return needs a settled movement, so it succeeds only when it runs after the settlement commits
        assert isinstance(results[0], Success), results
        return_ok = isinstance(results[1], Success)
        if not return_ok:
            assert isinstance(results[1], Failure)
            assert results[1].error.code == "INVALID_TRANSITION"

        assert scalar(
            path, "SELECT state FROM movements WHERE movement_id = 'mv-o'"
        ) == ("returned" if return_ok else "settled")
        for kind, effect, expected in (
            ("settlement", "outgoing_settlement", 1),
            ("return", "outgoing_return", int(return_ok)),
        ):
            assert (
                scalar(
                    path,
                    "SELECT COUNT(*) FROM movement_evidence WHERE movement_id = 'mv-o' AND evidence_kind = ?",
                    kind,
                )
                == expected
            )
            assert (
                scalar(
                    path,
                    "SELECT COUNT(*) FROM ledger_entries WHERE movement_id = 'mv-o' AND effect_kind = ?",
                    effect,
                )
                == expected
            )
