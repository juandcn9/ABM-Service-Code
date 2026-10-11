"""TASK-37: separate processes on one database file (TEST-14, TEST-17 in multi-process form; DEC-0071).

Each worker is a real OS process with its own connection. The parent sends the go signal on stdin, so the
race is started at the same moment in every process; assertions are on outcomes and stored state only.
"""

from __future__ import annotations

import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from abm.main import app_from_environment
from tests.integration.continuity_sequence import ROOT, STEPS, run_steps

WORKER = str(ROOT / "tests" / "integration" / "multiprocess_worker.py")


def set_env(
    monkeypatch: pytest.MonkeyPatch, db: pathlib.Path, busy_ms: int = 5000
) -> None:
    monkeypatch.setenv("ABM_MODE", "verification")
    monkeypatch.setenv("ABM_DB_PATH", str(db))
    monkeypatch.setenv("ABM_TRUSTED_INGRESS", "true")
    monkeypatch.setenv("ABM_CLOCK_MODE", "system")
    monkeypatch.setenv("ABM_BUSY_TIMEOUT_MS", str(busy_ms))


def funded_file(db: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two accounts; acct-a holds 1000 cents from the first four steps of the Specs sequence."""
    set_env(monkeypatch, db)
    client = TestClient(app_from_environment())
    run_steps(client, STEPS[:4])
    client.close()


def start(
    db: pathlib.Path, action: str, amount: int, busy_ms: int = 5000
) -> subprocess.Popen:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "ABM_BUSY_TIMEOUT_MS": str(busy_ms),
    }
    child = subprocess.Popen(
        [sys.executable, WORKER, str(db), action, str(amount)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=ROOT,
        env=env,
    )
    await_line(child, "READY")
    return child


def await_line(child: subprocess.Popen, prefix: str) -> str:
    """Skip the observability events the entry point also writes to stdout; return the first matching line."""
    assert child.stdout is not None
    for line in child.stdout:
        if line.startswith(prefix):
            return line.strip()
    raise AssertionError(f"the worker ended without printing {prefix}")


def finish(child: subprocess.Popen) -> str:
    assert child.stdin is not None
    child.stdin.write("go\n")
    child.stdin.flush()
    line = await_line(child, "RESULT")
    child.wait(timeout=60)
    return line


def balance(db: pathlib.Path) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-a'"
        ).fetchone()[0]
    finally:
        conn.close()


def test_two_processes_spending_the_same_funds_leave_at_most_one_success(
    tmp_path, monkeypatch
):
    db = tmp_path / "contend.sqlite3"
    funded_file(db, monkeypatch)
    first = start(db, "transfer", 1000)
    second = start(db, "transfer", 1000)
    results = sorted([finish(first), finish(second)])
    statuses = sorted(int(r.split()[1]) for r in results)
    assert statuses == [201, 422], results
    assert any(r.endswith("INSUFFICIENT_FUNDS") for r in results)
    assert balance(db) == 0  # exactly one debit of 1000 posted; never negative


def test_a_process_held_out_by_another_writer_gets_a_safe_busy_refusal_with_no_effect(
    tmp_path, monkeypatch
):
    db = tmp_path / "busy.sqlite3"
    funded_file(db, monkeypatch)
    worker = start(
        db, "transfer", 100, busy_ms=200
    )  # started first: its own startup must see a free file
    holder = sqlite3.connect(db, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")  # another process now holds the write lock
    try:
        result = finish(worker)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert result.split()[1:3] == ["503", "SERVICE_BUSY"], result
    assert balance(db) == 1000  # the refused command left no partial effect


def test_a_reader_process_keeps_its_snapshot_while_another_process_commits(
    tmp_path, monkeypatch
):
    db = tmp_path / "snapshot.sqlite3"
    funded_file(db, monkeypatch)
    reader = sqlite3.connect(db, isolation_level=None)
    try:
        reader.execute("BEGIN")
        before = reader.execute(
            "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-a'"
        ).fetchone()[0]
        writer = start(db, "credit", 50)
        result = finish(writer)
        assert result.split()[1:3] == ["200", "OK"], result
        inside = reader.execute(
            "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-a'"
        ).fetchone()[0]
        reader.execute("COMMIT")
        after = reader.execute(
            "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-a'"
        ).fetchone()[0]
    finally:
        reader.close()
    assert (
        before == 1000 and inside == 1000
    )  # the open snapshot does not see the other process's commit
    assert after == 1050  # a new read after the commit does
