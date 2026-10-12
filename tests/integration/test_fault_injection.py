"""Fault injection in verification mode only (TEST-38, specs/08 section 7).

Controlled sqlite3 errors are raised before and after every persistence write of one command and before its
commit. After reopening, the database must equal the pre-command snapshot and readiness must be clean. A
subprocess killed inside an open write transaction must recover the same way.
"""

from __future__ import annotations

import inspect
import pathlib
import re
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

import pytest

from abm.application.caller import CallerContext
from abm.application.closure import close_account
from abm.application.corrections import create_correction
from abm.application.idempotency import Response
from abm.application.legal_hold import set_legal_hold
from abm.application.outgoing_ach import settle_outgoing_ach
from abm.application.risk import set_risk_restriction
from abm.application.transfers import internal_transfer
from abm.domain.results import Failure, Result, Success
from abm.persistence import database, sqlite_store
from abm.persistence.readiness import readiness_reasons, start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import (
    MIGRATIONS,
    NOW,
    PAYER,
    clock,
    open_started,
    register,
    setup_funded,
    setup_submitted,
    snapshot,
)
from tests.integration.test_idempotency_conformance import (
    COMMANDS,
    KEY,
    START,
    SUCCESS,
)
from tests.integration.test_idempotency_conformance import (
    Command as ConformanceCommand,
)

REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")
RISK = CallerContext("risk-1", "risk_controller", "corr-r")
RETENTION = CallerContext("ret-1", "retention_controller", "corr-t")
CORRECTOR = CallerContext("corr-1", "correction_authority", "corr-x")


def _account_only(uow: SqliteUnitOfWork, clk: ControllableClock, scenario: str) -> None:
    register(uow, clk, "acct-a")


# write commands outside the conformance table: each needs only a registered account
ADMIN_COMMANDS: tuple[ConformanceCommand, ...] = (
    ConformanceCommand(
        "close_account",
        _account_only,
        lambda uow, clk, key, scenario, changed: close_account(
            uow, clk, REGISTRAR, key, "acct-a", {"instruction_id": "ins-cl"}
        ),
        "INVALID_TRANSITION",
        409,
    ),
    ConformanceCommand(
        "set_risk_restriction",
        _account_only,
        lambda uow, clk, key, scenario, changed: set_risk_restriction(
            uow,
            clk,
            RISK,
            key,
            "acct-a",
            {
                "instruction_id": "ins-rs",
                "action": "set",
                "decision_reference": "dec-rs",
            },
        ),
        "INVALID_TRANSITION",
        409,
    ),
    ConformanceCommand(
        "set_legal_hold",
        _account_only,
        lambda uow, clk, key, scenario, changed: set_legal_hold(
            uow,
            clk,
            RETENTION,
            key,
            "acct-a",
            {
                "instruction_id": "ins-lh",
                "record_type": "account",
                "record_id": "acct-a",
                "action": "set",
                "decision_reference": "dec-lh",
            },
        ),
        "INVALID_TRANSITION",
        409,
    ),
    ConformanceCommand(
        "create_correction",
        _account_only,
        lambda uow, clk, key, scenario, changed: create_correction(
            uow,
            clk,
            CORRECTOR,
            key,
            "acct-a",
            {
                "instruction_id": "ins-c1",
                "correction_id": "cor-1",
                "direction": "credit",
                "amount_cents": 500,
                "currency": "USD",
                "decision_reference": "dec-1",
            },
        ),
        "INVALID_TRANSITION",
        409,
    ),
)
ALL_COMMANDS: tuple[ConformanceCommand, ...] = (*COMMANDS, *ADMIN_COMMANDS)

# every method on SqliteWriteTransaction that issues an INSERT or UPDATE
MUTATORS = (
    "create_account",
    "create_movement",
    "set_movement_state",
    "add_evidence",
    "post_ledger",
    "apply_balance",
    "create_hold",
    "finalize_hold",
    "append_trace",
    "save_outcome",
    "set_restriction",
    "close_account",
    "set_retention_dates",
    "set_legal_hold",
)

Command = Callable[[SqliteUnitOfWork], Result[Response]]


class Plan:
    """Counts write boundaries; raises at boundary `target` (1-based) in `phase`."""

    def __init__(self, target: int | None, phase: str, error: type[Exception]) -> None:
        self.target = target
        self.phase = phase  # "before", "after", "commit", or "none"
        self.error = error
        self.calls = 0


def _wrap(original: Callable[..., Any], plan: Plan) -> Callable[..., Any]:
    def wrapper(self: object, *args: object, **kwargs: object) -> object:
        plan.calls += 1
        hit = plan.target == plan.calls
        if hit and plan.phase == "before":
            raise plan.error("injected fault before write")
        result = original(self, *args, **kwargs)
        if hit and plan.phase == "after":
            raise plan.error("injected fault after write")
        return result

    return wrapper


def _commit_wrapper(plan: Plan) -> Callable[[sqlite3.Connection], Any]:
    real = database.write_transaction

    @contextmanager
    def failing_before_commit(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        with real(conn) as tx:
            yield tx
            # the body has finished; raising here makes write_transaction roll back instead of COMMIT
            if plan.phase == "commit":
                raise plan.error("injected fault before commit")

    return failing_before_commit


@contextmanager
def instrumented(plan: Plan) -> Iterator[None]:
    with ExitStack() as stack:
        for name in MUTATORS:
            original = getattr(sqlite_store.SqliteWriteTransaction, name)
            stack.enter_context(
                patch.object(
                    sqlite_store.SqliteWriteTransaction, name, _wrap(original, plan)
                )
            )
        stack.enter_context(
            patch.object(sqlite_store, "write_transaction", _commit_wrapper(plan))
        )
        yield


class _Generic(sqlite3.OperationalError):
    """No sqlite_errorcode: maps to INTERNAL_ERROR."""


class _Plain(RuntimeError):
    """Not a sqlite error at all: must roll back and map to INTERNAL_ERROR."""


class _Busy(sqlite3.OperationalError):
    sqlite_errorcode = 5  # SQLITE_BUSY: maps to SERVICE_BUSY, retryable


class _Full(sqlite3.OperationalError):
    sqlite_errorcode = 13  # SQLITE_FULL: maps to SERVICE_UNREADY


ERRORS: dict[str, tuple[type[Exception], str]] = {
    "generic": (_Generic, "INTERNAL_ERROR"),
    "busy": (_Busy, "SERVICE_BUSY"),
    "full": (_Full, "SERVICE_UNREADY"),
    # not a sqlite error: exercises the write() branch for unexpected exceptions (TEST-28)
    "plain": (_Plain, "INTERNAL_ERROR"),
}


def transfer_command(uow: SqliteUnitOfWork) -> Result[Response]:
    body = {
        "instruction_id": "ins-t",
        "movement_id": "mv-t",
        "source_account_id": "acct-a",
        "destination_account_id": "acct-b",
        "amount_cents": 300,
        "currency": "USD",
    }
    return internal_transfer(uow, clock(), PAYER, "kt", body)


def settle_command(uow: SqliteUnitOfWork) -> Result[Response]:
    evidence = {"instruction_id": "ins-st", "evidence_reference": "ev-st"}
    return settle_outgoing_ach(uow, clock(), PAYER, "kst", "acct-a", "mv-o", evidence)


# scenario name -> (setup that leaves the database ready for the command, the command)
SCENARIOS: dict[str, tuple[Callable[[pathlib.Path], None], Command]] = {
    "internal_transfer": (setup_funded, transfer_command),
    "outgoing_settlement": (setup_submitted, settle_command),
}


def count_writes(
    path: pathlib.Path, setup: Callable[[pathlib.Path], None], command: Command
) -> int:
    setup(path)
    conn = open_started(path)
    try:
        plan = Plan(None, "none", _Generic)
        with instrumented(plan):
            command(SqliteUnitOfWork(conn))
        return plan.calls
    finally:
        conn.close()


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
@pytest.mark.parametrize("kind", sorted(ERRORS))
def test_a_fault_at_any_write_or_before_commit_leaves_the_pre_command_snapshot(
    tmp_path: pathlib.Path, scenario: str, kind: str
) -> None:
    setup, command = SCENARIOS[scenario]
    error, code = ERRORS[kind]
    writes = count_writes(tmp_path / "count.sqlite3", setup, command)
    assert writes >= 5  # the sweep must actually cover the command's writes

    points: list[tuple[int | None, str]] = [
        (n, phase) for n in range(1, writes + 1) for phase in ("before", "after")
    ]
    points.append((None, "commit"))

    for index, (target, phase) in enumerate(points):
        path = tmp_path / f"{scenario}-{kind}-{index}.sqlite3"
        setup(path)
        conn = open_started(path)
        before = snapshot(conn)

        with instrumented(Plan(target, phase, error)):
            result = command(SqliteUnitOfWork(conn))
        conn.close()

        where = (target, phase)
        assert isinstance(result, Failure), where
        assert result.error.code == code, where
        assert result.error.retryable == (kind == "busy"), where

        # reopen as a restart would: recovery, readiness, and the pre-command snapshot
        reopened = start_database(path, MIGRATIONS, NOW)
        assert reopened.ready, (where, reopened.reasons)
        assert reopened.connection is not None
        try:
            assert readiness_reasons(reopened.connection, MIGRATIONS) == []
            assert snapshot(reopened.connection) == before, where
            # no orphaned outcome: the same request now applies exactly once
            retry = command(SqliteUnitOfWork(reopened.connection))
            assert isinstance(retry, Success), where
        finally:
            reopened.connection.close()


def _command_db(
    path: pathlib.Path, command: Any
) -> tuple[Any, SqliteUnitOfWork, ControllableClock]:
    conn = open_started(path)
    uow, clk = SqliteUnitOfWork(conn), ControllableClock(START)
    command.prepare(uow, clk, SUCCESS)
    return conn, uow, clk


@pytest.mark.parametrize("kind", sorted(ERRORS))
@pytest.mark.parametrize("command", ALL_COMMANDS, ids=[c.name for c in ALL_COMMANDS])
def test_every_write_command_leaves_the_pre_command_snapshot_under_a_fault(
    tmp_path: pathlib.Path, command: Any, kind: str
) -> None:
    # TEST-16: the sweep covers every write command in the conformance table, not only two
    error, code = ERRORS[kind]
    conn, uow, clk = _command_db(tmp_path / "count.sqlite3", command)
    plan = Plan(None, "none", _Generic)
    with instrumented(plan):
        command.call(uow, clk, KEY, SUCCESS, False)
    conn.close()
    writes = plan.calls
    assert writes >= 2, command.name  # at least one effect plus the stored outcome

    points: list[tuple[int | None, str]] = [
        (n, phase) for n in range(1, writes + 1) for phase in ("before", "after")
    ]
    points.append((None, "commit"))

    for index, (target, phase) in enumerate(points):
        path = tmp_path / f"{command.name}-{kind}-{index}.sqlite3"
        conn, uow, clk = _command_db(path, command)
        before = snapshot(conn)
        with instrumented(Plan(target, phase, error)):
            result = command.call(uow, clk, KEY, SUCCESS, False)
        conn.close()

        where = (command.name, target, phase)
        assert isinstance(result, Failure), where
        assert result.error.code == code, where
        assert result.error.retryable == (kind == "busy"), where

        reopened = start_database(path, MIGRATIONS, NOW)
        assert reopened.ready, (where, reopened.reasons)
        assert reopened.connection is not None
        try:
            assert readiness_reasons(reopened.connection, MIGRATIONS) == []
            assert snapshot(reopened.connection) == before, where
            retry = command.call(
                SqliteUnitOfWork(reopened.connection),
                ControllableClock(START),
                KEY,
                SUCCESS,
                False,
            )
            assert isinstance(retry, Success), where
        finally:
            reopened.connection.close()


def test_every_sql_writing_method_is_instrumented() -> None:
    # guard: a write method missing from MUTATORS would be skipped silently by the sweep (TEST-16)
    writers = {
        name
        for name, fn in vars(sqlite_store.SqliteWriteTransaction).items()
        if not name.startswith("_")
        and callable(fn)
        and re.search(r"\b(INSERT|UPDATE|DELETE)\b", inspect.getsource(fn))
    }
    assert writers == set(MUTATORS)


# ---- section 7 recovery: a subprocess killed inside an open write transaction ----

CHILD = r"""
import pathlib
import sys
from datetime import UTC, datetime
src, root, db = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [src, root]
from abm.application.caller import CallerContext
from abm.application.transfers import internal_transfer
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork, SqliteWriteTransaction
from abm.persistence.migrations import load_migrations
from harness.clock import ControllableClock

original = SqliteWriteTransaction.apply_balance

def stop_inside_the_transaction(self, account_id, delta_cents):
    original(self, account_id, delta_cents)  # the source debit is applied, nothing is committed
    sys.stdout.write("in-transaction\n")
    sys.stdout.flush()
    sys.stdin.read()  # block until the parent kills this process

SqliteWriteTransaction.apply_balance = stop_inside_the_transaction
started = start_database(db, load_migrations(pathlib.Path(root) / "migrations"), "2026-10-10T12:00:00Z")
caller = CallerContext("pay-1", "payment_orchestrator", "corr-p")
body = {
    "instruction_id": "ins-kill",
    "movement_id": "mv-kill",
    "source_account_id": "acct-a",
    "destination_account_id": "acct-b",
    "amount_cents": 300,
    "currency": "USD",
}
clock = ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
internal_transfer(SqliteUnitOfWork(started.connection), clock, caller, "kkill", body)
"""


def test_a_subprocess_killed_inside_a_write_recovers_with_no_partial_effect(
    tmp_path: pathlib.Path,
) -> None:
    db = tmp_path / "kill.sqlite3"
    setup_funded(db)
    conn = open_started(db)
    before = snapshot(conn)
    conn.close()

    root = pathlib.Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, "-I", "-c", CHILD, str(root / "src"), str(root), str(db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # watchdog: a hung child is killed rather than blocking the suite
    watchdog = threading.Timer(60, proc.kill)
    watchdog.start()
    try:
        assert proc.stdout is not None
        # barrier: the child reports that it is inside the open transaction, with a debit applied
        assert (
            proc.stdout.readline().strip() == b"in-transaction"
        )  # text mode adds CRLF on Windows
        proc.kill()
        proc.wait(timeout=30)
    finally:
        watchdog.cancel()
    assert proc.returncode != 0

    reopened = start_database(db, MIGRATIONS, NOW)
    assert reopened.ready, reopened.reasons
    assert reopened.connection is not None
    try:
        assert readiness_reasons(reopened.connection, MIGRATIONS) == []
        # SQLite discards the uncommitted frames: the state equals the pre-command snapshot
        assert snapshot(reopened.connection) == before
        retry = internal_transfer(
            SqliteUnitOfWork(reopened.connection),
            clock(),
            PAYER,
            "kkill",
            {
                "instruction_id": "ins-kill",
                "movement_id": "mv-kill",
                "source_account_id": "acct-a",
                "destination_account_id": "acct-b",
                "amount_cents": 300,
                "currency": "USD",
            },
        )
        assert isinstance(retry, Success)
        assert readiness_reasons(reopened.connection, MIGRATIONS) == []
    finally:
        reopened.connection.close()
