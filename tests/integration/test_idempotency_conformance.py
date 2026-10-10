"""Cross-flow idempotency conformance (TASK-17, TEST-15, TEST-46, DEC-0011).

One table covers every state-changing command. For each command, in a success scenario and in a
deterministic-rejection scenario: the first call stores exactly one outcome; the same key and
fingerprint replays it exactly (replayed=True) with no writes; the same key with one changed field
conflicts with no writes. Failures that must not be stored (INTERNAL_ERROR, SERVICE_UNREADY) leave
the key free, so a later request with the same key is evaluated fresh.
"""

from __future__ import annotations

import pathlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from abm.application.caller import CallerContext
from abm.application.cards import (
    authorize_card,
    clear_card,
    expire_card,
    refund_card,
    reverse_card,
)
from abm.application.idempotency import Response
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
from abm.application.reads import get_account
from abm.application.registration import register_account
from abm.application.transfers import internal_transfer
from abm.domain.results import Failure, Result, Success
from abm.persistence import sqlite_store
from abm.persistence.migrations import load_migrations
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = load_migrations(ROOT / "migrations")
NOW = "2026-10-10T12:00:00Z"
START = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
CARD = CallerContext("card-1", "card_orchestrator", "corr-c")
READER = CallerContext("reader-1", "account_reader", "corr-r", "acct-1")
KEY = "k-under-test"
SUCCESS = "success"
REJECTION = "rejection"
TABLES = (
    "accounts",
    "movements",
    "movement_evidence",
    "ledger_entries",
    "audit_trace",
    "holds",
    "idempotency_outcomes",
)


class BrokenClock(ControllableClock):
    def now(self) -> datetime:
        raise RuntimeError("clock down")


@pytest.fixture
def conn(tmp_path: pathlib.Path) -> sqlite3.Connection:
    started = start_database(tmp_path / "abm.sqlite3", MIGRATIONS, NOW)
    assert started.connection is not None
    return started.connection


@pytest.fixture
def uow(conn: sqlite3.Connection) -> SqliteUnitOfWork:
    return SqliteUnitOfWork(conn)


@pytest.fixture
def clock() -> ControllableClock:
    return ControllableClock(START)


def counts(conn: sqlite3.Connection) -> tuple[int, ...]:
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES
    )


def stored(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """The outcomes stored under the key under test (one scope per command)."""
    return conn.execute(
        "SELECT outcome_class, http_status FROM idempotency_outcomes"
        " WHERE idempotency_key = ?",
        (KEY,),
    ).fetchall()


# --- setup helpers (pre-* keys never collide with KEY) -------------------------------------


def register_body(
    account: str, customer: str, instruction: str, eligibility: str = "elig-1"
) -> dict[str, object]:
    return {
        "instruction_id": instruction,
        "account_id": account,
        "customer_id": customer,
        "currency": "USD",
        "eligibility_reference": eligibility,
    }


def setup_account(
    uow: SqliteUnitOfWork,
    clock: ControllableClock,
    account: str = "acct-1",
    customer: str = "cust-1",
) -> None:
    body = register_body(account, customer, f"ins-reg-{account}")
    result = register_account(uow, clock, REGISTRAR, f"pre-reg-{account}", body)
    assert isinstance(result, Success), result


def notice(
    uow: SqliteUnitOfWork,
    clock: ControllableClock,
    movement: str = "mv-in",
    cents: int = 1000,
    account: str = "acct-1",
) -> None:
    body = {
        "instruction_id": f"ins-{movement}",
        "movement_id": movement,
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": f"ext-{movement}",
    }
    result = create_incoming_ach(uow, clock, PAYER, f"pre-n-{movement}", account, body)
    assert isinstance(result, Success), result


def settle_notice(
    uow: SqliteUnitOfWork,
    clock: ControllableClock,
    movement: str = "mv-in",
    account: str = "acct-1",
) -> None:
    body = {
        "instruction_id": f"ins-s-{movement}",
        "evidence_reference": f"ev-{movement}",
    }
    result = settle_incoming_ach(
        uow, clock, PAYER, f"pre-s-{movement}", account, movement, body
    )
    assert isinstance(result, Success), result


def funded(
    uow: SqliteUnitOfWork,
    clock: ControllableClock,
    account: str = "acct-1",
    cents: int = 1000,
) -> None:
    setup_account(uow, clock, account, "cust-" + account.removeprefix("acct-"))
    notice(uow, clock, "mv-in", cents, account)
    settle_notice(uow, clock, "mv-in", account)


def outgoing_body(movement: str, cents: int) -> dict[str, object]:
    return {
        "instruction_id": f"ins-{movement}",
        "movement_id": movement,
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": f"ext-{movement}",
        "destination_reference": "dest-1",
    }


def create_outgoing(
    uow: SqliteUnitOfWork, clock: ControllableClock, movement: str = "mv-out"
) -> None:
    result = create_outgoing_ach(
        uow, clock, PAYER, f"pre-c-{movement}", "acct-1", outgoing_body(movement, 400)
    )
    assert isinstance(result, Success), result


def evidence_body(ref: str) -> dict[str, object]:
    return {"instruction_id": f"ins-{ref}", "evidence_reference": ref}


def amount_body(ref: str, cents: int) -> dict[str, object]:
    return {
        "instruction_id": f"ins-{ref}",
        "evidence_reference": ref,
        "amount_cents": cents,
        "currency": "USD",
    }


def authorize_setup(uow: SqliteUnitOfWork, clock: ControllableClock) -> None:
    body = {
        "instruction_id": "ins-mv-card",
        "movement_id": "mv-card",
        "amount_cents": 400,
        "currency": "USD",
        "external_reference": "ext-mv-card",
        "merchant_reference": "merchant-1",
    }
    result = authorize_card(uow, clock, CARD, "pre-a", "acct-1", body)
    assert isinstance(result, Success), result


def clear_setup(uow: SqliteUnitOfWork, clock: ControllableClock) -> None:
    result = clear_card(
        uow, clock, CARD, "pre-cl", "acct-1", "mv-card", amount_body("ev-pre", 400)
    )
    assert isinstance(result, Success), result


# --- the command table ---------------------------------------------------------------------


@dataclass(frozen=True)
class Command:
    name: str
    # sets up state; the scenario decides whether the success or the rejection path is reachable
    prepare: Callable[[SqliteUnitOfWork, ControllableClock, str], None]
    # one call with KEY; changed=True alters exactly one field
    call: Callable[
        [SqliteUnitOfWork, ControllableClock, str, str, bool], Result[Response]
    ]
    reject_code: str
    reject_status: int


def _register_prepare(uow, clock, scenario):
    if scenario == REJECTION:
        setup_account(uow, clock)


def _register_call(uow, clock, key, scenario, changed):
    if scenario == SUCCESS:
        body = register_body(
            "acct-2", "cust-2", "ins-2", "elig-9" if changed else "elig-1"
        )
    else:
        # the customer is the scope (specs/02), so a changed customer is a new scope, not a conflict
        body = register_body("acct-1", "cust-9", "ins-8" if changed else "ins-9")
    return register_account(uow, clock, REGISTRAR, key, body)


def _notice_prepare(uow, clock, scenario):
    setup_account(uow, clock)


def _notice_call(uow, clock, key, scenario, changed):
    account = "acct-1" if scenario == SUCCESS else "acct-missing"
    body = {
        "instruction_id": "ins-n",
        "movement_id": "mv-1",
        "amount_cents": 501 if changed else 500,
        "currency": "USD",
        "external_reference": "ext-1",
    }
    return create_incoming_ach(uow, clock, PAYER, key, account, body)


def _incoming_settle_prepare(uow, clock, scenario):
    setup_account(uow, clock)
    notice(uow, clock, "mv-1", 500)


def _incoming_settle_call(uow, clock, key, scenario, changed):
    account = "acct-1" if scenario == SUCCESS else "acct-missing"
    evidence = "ev-2" if changed else "ev-1"
    body = {"instruction_id": "ins-s", "evidence_reference": evidence}
    return settle_incoming_ach(uow, clock, PAYER, key, account, "mv-1", body)


def _incoming_return_prepare(uow, clock, scenario):
    setup_account(uow, clock)
    notice(uow, clock, "mv-1", 500)
    settle_notice(uow, clock, "mv-1")


def _incoming_return_call(uow, clock, key, scenario, changed):
    # a mismatched amount is the deterministic rejection (AMOUNT_MISMATCH, 422)
    amount = 500 if scenario == SUCCESS else 499
    body = {
        "instruction_id": "ins-r",
        "evidence_reference": "ev-2" if changed else "ev-r",
        "amount_cents": amount,
        "currency": "USD",
    }
    return return_incoming_ach(uow, clock, PAYER, key, "acct-1", "mv-1", body)


def _outgoing_create_prepare(uow, clock, scenario):
    funded(uow, clock)


def _outgoing_create_call(uow, clock, key, scenario, changed):
    if scenario == SUCCESS:
        cents = 401 if changed else 400
    else:
        cents = 5001 if changed else 5000  # more than the 1000 available: 422
    return create_outgoing_ach(
        uow, clock, PAYER, key, "acct-1", outgoing_body("mv-out", cents)
    )


def _outgoing_submit_prepare(uow, clock, scenario):
    funded(uow, clock)
    create_outgoing(uow, clock)


def _outgoing_submit_call(uow, clock, key, scenario, changed):
    account = "acct-1" if scenario == SUCCESS else "acct-missing"
    body = evidence_body("ev-2" if changed else "ev-sub")
    return submit_outgoing_ach(uow, clock, PAYER, key, account, "mv-out", body)


def _outgoing_settle_prepare(uow, clock, scenario):
    funded(uow, clock)
    create_outgoing(uow, clock)
    if scenario == SUCCESS:
        body = evidence_body("ev-sub")
        result = submit_outgoing_ach(
            uow, clock, PAYER, "pre-sub", "acct-1", "mv-out", body
        )
        assert isinstance(result, Success), result


def _outgoing_settle_call(uow, clock, key, scenario, changed):
    # on an accepted (not submitted) movement settlement is INVALID_TRANSITION (409)
    body = evidence_body("ev-2" if changed else "ev-s")
    return settle_outgoing_ach(uow, clock, PAYER, key, "acct-1", "mv-out", body)


def _outgoing_reject_prepare(uow, clock, scenario):
    _outgoing_settle_prepare(uow, clock, scenario)


def _outgoing_reject_call(uow, clock, key, scenario, changed):
    body = evidence_body("ev-2" if changed else "ev-rej")
    return reject_outgoing_ach(uow, clock, PAYER, key, "acct-1", "mv-out", body)


def _outgoing_cancel_prepare(uow, clock, scenario):
    funded(uow, clock)
    create_outgoing(uow, clock)
    if scenario == REJECTION:
        body = evidence_body("ev-sub")
        result = submit_outgoing_ach(
            uow, clock, PAYER, "pre-sub", "acct-1", "mv-out", body
        )
        assert isinstance(result, Success), result


def _outgoing_cancel_call(uow, clock, key, scenario, changed):
    body = evidence_body("ev-2" if changed else "ev-can")
    return cancel_outgoing_ach(uow, clock, PAYER, key, "acct-1", "mv-out", body)


def _outgoing_return_prepare(uow, clock, scenario):
    _outgoing_settle_prepare(uow, clock, SUCCESS)
    body = evidence_body("ev-sett")
    result = settle_outgoing_ach(uow, clock, PAYER, "pre-set", "acct-1", "mv-out", body)
    assert isinstance(result, Success), result


def _outgoing_return_call(uow, clock, key, scenario, changed):
    # a return that differs from the settled 400 is AMOUNT_MISMATCH (422)
    amount = 400 if scenario == SUCCESS else 399
    body = amount_body("ev-2" if changed else "ev-ret", amount)
    return return_outgoing_ach(uow, clock, PAYER, key, "acct-1", "mv-out", body)


def _transfer_prepare(uow, clock, scenario):
    setup_account(uow, clock, "acct-1", "cust-1")
    setup_account(uow, clock, "acct-2", "cust-2")
    notice(uow, clock, "mv-in", 1000, "acct-1")
    settle_notice(uow, clock, "mv-in", "acct-1")


def _transfer_call(uow, clock, key, scenario, changed):
    if scenario == SUCCESS:
        cents = 301 if changed else 300
    else:
        cents = 5001 if changed else 5000  # more than the 1000 available: 422
    body = {
        "instruction_id": "ins-t",
        "movement_id": "mv-t",
        "source_account_id": "acct-1",
        "destination_account_id": "acct-2",
        "amount_cents": cents,
        "currency": "USD",
    }
    return internal_transfer(uow, clock, PAYER, key, body)


def _authorize_prepare(uow, clock, scenario):
    funded(uow, clock)


def _authorize_call(uow, clock, key, scenario, changed):
    cents = 5000 if scenario == REJECTION else 400
    if changed:
        cents += 1
    body = {
        "instruction_id": "ins-mv-card",
        "movement_id": "mv-card",
        "amount_cents": cents,
        "currency": "USD",
        "external_reference": "ext-mv-card",
        "merchant_reference": "merchant-1",
    }
    return authorize_card(uow, clock, CARD, key, "acct-1", body)


def _clear_prepare(uow, clock, scenario):
    funded(uow, clock)
    authorize_setup(uow, clock)


def _clear_call(uow, clock, key, scenario, changed):
    account = "acct-1" if scenario == SUCCESS else "acct-missing"
    cents = 399 if changed else 400
    return clear_card(
        uow, clock, CARD, key, account, "mv-card", amount_body("ev-c", cents)
    )


def _release_prepare(
    uow: SqliteUnitOfWork, clock: ControllableClock, scenario: str
) -> None:
    funded(uow, clock)
    authorize_setup(uow, clock)
    if scenario == REJECTION:
        clear_setup(
            uow, clock
        )  # a cleared movement cannot be released: INVALID_TRANSITION


def _reverse_call(uow, clock, key, scenario, changed):
    return reverse_card(
        uow,
        clock,
        CARD,
        key,
        "acct-1",
        "mv-card",
        evidence_body("ev-2" if changed else "ev-rv"),
    )


def _expire_call(uow, clock, key, scenario, changed):
    return expire_card(
        uow,
        clock,
        CARD,
        key,
        "acct-1",
        "mv-card",
        evidence_body("ev-2" if changed else "ev-ex"),
    )


def _refund_prepare(uow, clock, scenario):
    funded(uow, clock)
    authorize_setup(uow, clock)
    if scenario == SUCCESS:
        clear_setup(
            uow, clock
        )  # a refund needs a cleared movement; before that it is INVALID_TRANSITION


def _refund_call(uow, clock, key, scenario, changed):
    cents = 399 if changed else 400
    return refund_card(
        uow, clock, CARD, key, "acct-1", "mv-card", amount_body("ev-f", cents)
    )


COMMANDS: tuple[Command, ...] = (
    Command(
        "register_account", _register_prepare, _register_call, "DUPLICATE_ACCOUNT", 409
    ),
    Command("incoming_notice", _notice_prepare, _notice_call, "ACCOUNT_NOT_FOUND", 404),
    Command(
        "incoming_settle",
        _incoming_settle_prepare,
        _incoming_settle_call,
        "ACCOUNT_NOT_FOUND",
        404,
    ),
    Command(
        "incoming_return",
        _incoming_return_prepare,
        _incoming_return_call,
        "AMOUNT_MISMATCH",
        422,
    ),
    Command(
        "outgoing_create",
        _outgoing_create_prepare,
        _outgoing_create_call,
        "INSUFFICIENT_FUNDS",
        422,
    ),
    Command(
        "outgoing_submit",
        _outgoing_submit_prepare,
        _outgoing_submit_call,
        "ACCOUNT_NOT_FOUND",
        404,
    ),
    Command(
        "outgoing_settle",
        _outgoing_settle_prepare,
        _outgoing_settle_call,
        "INVALID_TRANSITION",
        409,
    ),
    Command(
        "outgoing_reject",
        _outgoing_reject_prepare,
        _outgoing_reject_call,
        "INVALID_TRANSITION",
        409,
    ),
    Command(
        "outgoing_cancel",
        _outgoing_cancel_prepare,
        _outgoing_cancel_call,
        "INVALID_TRANSITION",
        409,
    ),
    Command(
        "outgoing_return",
        _outgoing_return_prepare,
        _outgoing_return_call,
        "AMOUNT_MISMATCH",
        422,
    ),
    Command(
        "internal_transfer",
        _transfer_prepare,
        _transfer_call,
        "INSUFFICIENT_FUNDS",
        422,
    ),
    Command(
        "card_authorize", _authorize_prepare, _authorize_call, "INSUFFICIENT_FUNDS", 422
    ),
    Command("card_clear", _clear_prepare, _clear_call, "ACCOUNT_NOT_FOUND", 404),
    Command("card_reverse", _release_prepare, _reverse_call, "INVALID_TRANSITION", 409),
    Command("card_expire", _release_prepare, _expire_call, "INVALID_TRANSITION", 409),
    Command("card_refund", _refund_prepare, _refund_call, "INVALID_TRANSITION", 409),
)
IDS = [command.name for command in COMMANDS]


# --- conformance -----------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", [SUCCESS, REJECTION])
@pytest.mark.parametrize("command", COMMANDS, ids=IDS)
def test_replay_and_conflict_store_and_return_exactly_one_outcome(
    command: Command,
    scenario: str,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    command.prepare(uow, clock, scenario)
    first = command.call(uow, clock, KEY, scenario, False)
    if scenario == SUCCESS:
        assert isinstance(first, Success) and first.replayed is False, first
        expected = [("success", first.value.status)]
    else:
        assert isinstance(first, Failure) and first.replayed is False, first
        assert first.error.code == command.reject_code
        expected = [("deterministic_rejection", command.reject_status)]
    assert stored(conn) == expected
    before = counts(conn)

    # (a) same key and fingerprint: the stored outcome, exactly, and no new writes
    again = command.call(uow, clock, KEY, scenario, False)
    if scenario == SUCCESS:
        assert isinstance(again, Success) and isinstance(first, Success)
        assert again.replayed is True and again.value == first.value
    else:
        assert isinstance(again, Failure) and isinstance(first, Failure)
        assert again.replayed is True and again.error == first.error
    assert counts(conn) == before

    # (b) same key, one changed field: conflict, nothing written, original still intact
    changed = command.call(uow, clock, KEY, scenario, True)
    assert isinstance(changed, Failure) and changed.replayed is False
    assert changed.error.code == "IDEMPOTENCY_CONFLICT"
    assert counts(conn) == before
    assert stored(conn) == expected


# --- non-stored failures: INTERNAL_ERROR (500) and SERVICE_UNREADY (503) -------------------


@pytest.mark.parametrize("scenario", [SUCCESS, REJECTION])
@pytest.mark.parametrize("command", COMMANDS, ids=IDS)
def test_service_unready_is_not_stored_and_the_key_is_evaluated_fresh(
    command: Command,
    scenario: str,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
) -> None:
    command.prepare(uow, clock, scenario)
    before = counts(conn)
    down = command.call(uow, BrokenClock(START), KEY, scenario, False)
    assert isinstance(down, Failure) and down.replayed is False
    assert down.error.code == "SERVICE_UNREADY"
    assert counts(conn) == before and stored(conn) == []

    fresh = command.call(uow, clock, KEY, scenario, False)
    assert fresh.replayed is False
    if scenario == SUCCESS:
        assert isinstance(fresh, Success)
        assert stored(conn) == [("success", fresh.value.status)]
    else:
        assert isinstance(fresh, Failure) and fresh.error.code == command.reject_code
        assert stored(conn) == [("deterministic_rejection", command.reject_status)]


@pytest.mark.parametrize("scenario", [SUCCESS, REJECTION])
@pytest.mark.parametrize("command", COMMANDS, ids=IDS)
def test_internal_error_is_not_stored_and_the_key_is_evaluated_fresh(
    command: Command,
    scenario: str,
    uow: SqliteUnitOfWork,
    conn: sqlite3.Connection,
    clock: ControllableClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.prepare(uow, clock, scenario)
    before = counts(conn)

    # the outcome write is the last step of every command; a fault there must roll all back
    def fault(self: object, *args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("injected fault")

    monkeypatch.setattr(sqlite_store.SqliteWriteTransaction, "save_outcome", fault)
    down = command.call(uow, clock, KEY, scenario, False)
    monkeypatch.undo()
    assert isinstance(down, Failure) and down.replayed is False
    assert down.error.code == "INTERNAL_ERROR"
    assert counts(conn) == before and stored(conn) == []

    fresh = command.call(uow, clock, KEY, scenario, False)
    assert fresh.replayed is False
    if scenario == SUCCESS:
        assert isinstance(fresh, Success)
        assert stored(conn) == [("success", fresh.value.status)]
    else:
        assert isinstance(fresh, Failure) and fresh.error.code == command.reject_code
        assert stored(conn) == [("deterministic_rejection", command.reject_status)]


def test_pre_idempotency_failures_are_not_stored(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    # 400 (invalid body) and 403 (wrong role) are refused before any idempotency record exists
    before = counts(conn)
    invalid = register_account(uow, clock, REGISTRAR, KEY, {"instruction_id": "x"})
    assert isinstance(invalid, Failure) and invalid.error.code == "VALIDATION_ERROR"
    denied = register_account(uow, clock, PAYER, KEY, register_body("acct-1", "c", "i"))
    assert isinstance(denied, Failure) and denied.error.code == "FORBIDDEN_SCOPE"
    assert counts(conn) == before and stored(conn) == []

    fresh = register_account(
        uow, clock, REGISTRAR, KEY, register_body("acct-1", "c", "i")
    )
    assert isinstance(fresh, Success) and fresh.replayed is False


def test_reads_store_no_idempotency_outcome(
    uow: SqliteUnitOfWork, conn: sqlite3.Connection, clock: ControllableClock
) -> None:
    setup_account(uow, clock)
    before = counts(conn)
    first = get_account(uow, READER, "acct-1")
    again = get_account(uow, READER, "acct-1")
    assert isinstance(first, Success) and isinstance(again, Success)
    assert counts(conn) == before
