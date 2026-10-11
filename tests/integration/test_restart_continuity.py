"""TASK-28: restart continuity and abrupt-termination recovery on the same database file (TEST-17, NFR-03).

Graceful: run the Specs section 5 sequence, close, reopen the same file, and expect identical state and an exact
idempotent replay. Abrupt: kill a worker process mid-sequence; the reopened file must equal a clean prefix of
the sequence (the in-flight step either fully committed or fully absent). Assertions are on outcomes only.
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

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def set_env(monkeypatch: pytest.MonkeyPatch, db: pathlib.Path) -> None:
    monkeypatch.setenv("ABM_MODE", "verification")
    monkeypatch.setenv("ABM_DB_PATH", str(db))
    monkeypatch.setenv("ABM_TRUSTED_INGRESS", "true")
    monkeypatch.setenv("ABM_CLOCK_MODE", "system")


def snapshot(db: pathlib.Path) -> dict[str, list[tuple]]:
    """Stored facts only: accounts and balances, movements and states, ledger, trace. Read after close."""
    conn = sqlite3.connect(db)
    try:
        return {
            "accounts": conn.execute(
                "SELECT account_id, status, restriction, current_balance_cents FROM accounts ORDER BY account_id"
            ).fetchall(),
            "movements": conn.execute(
                "SELECT movement_id, state, amount_cents FROM movements ORDER BY movement_id"
            ).fetchall(),
            "ledger": conn.execute(
                "SELECT entry_id, account_id, effect_kind, direction, amount_cents FROM ledger_entries "
                "ORDER BY entry_id"
            ).fetchall(),
            "trace": conn.execute("SELECT COUNT(*) FROM audit_trace").fetchall(),
        }
    finally:
        conn.close()


def fresh_prefix(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> dict[str, list[tuple]]:
    """The state after the first `count` steps, from a clean file, run through the same entry point."""
    db = tmp_path / f"prefix-{count}.sqlite3"
    set_env(monkeypatch, db)
    client = TestClient(app_from_environment())
    run_steps(client, STEPS[:count])
    client.close()
    return snapshot(db)


EXPECTED_ACCOUNTS = [("acct-a", "none", 460), ("acct-b", "outgoing_blocked", 50)]
EXPECTED_MOVEMENTS = [
    ("cor-1", "completed", 10),
    ("mv-c1", "cleared", 300),
    ("mv-n1", "settled", 1000),
    ("mv-o1", "settled", 200),
    ("mv-t1", "completed", 50),
]


def test_a_graceful_restart_on_the_same_file_preserves_state_and_replays_exactly(
    tmp_path, monkeypatch
):
    db = tmp_path / "graceful.sqlite3"
    set_env(monkeypatch, db)
    first = TestClient(app_from_environment())
    run_steps(first, STEPS)
    original = first.request(
        "POST", "/v1/accounts/registrations", json=STEPS[0][3], headers=STEPS[0][4]
    )
    first.close()

    before = snapshot(db)
    # the expected end state is fixed by the business rules, not only by comparing the file to itself
    assert [(a, r, b) for a, _status, r, b in before["accounts"]] == EXPECTED_ACCOUNTS
    assert before["movements"] == EXPECTED_MOVEMENTS

    second = TestClient(app_from_environment())
    assert second.get("/health/ready").status_code == 200
    replay = second.request(
        "POST", "/v1/accounts/registrations", json=STEPS[0][3], headers=STEPS[0][4]
    )
    second.close()

    assert snapshot(db) == before
    assert replay.status_code == 201
    assert replay.json()["data"] == original.json()["data"]
    assert replay.json()["meta"].get("replayed") is True


@pytest.mark.parametrize("killed_after", [3, 7, 11])
def test_an_abrupt_kill_mid_sequence_recovers_to_the_exact_prefix(
    tmp_path, monkeypatch, killed_after
):
    db = tmp_path / f"killed-{killed_after}.sqlite3"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    child = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tests" / "integration" / "continuity_sequence.py"),
            str(db),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=ROOT,
        env=env,
    )
    done = 0
    try:
        for line in child.stdout:
            if not line.startswith("DONE "):
                continue
            done = int(line.split()[1]) + 1
            if done == killed_after:
                break
            child.stdin.write(
                "go\n"
            )  # the child is paused after each committed step; let it run on
            child.stdin.flush()
    finally:
        child.kill()
        child.wait(timeout=30)
        child.stdout.close()
        child.stdin.close()

    # the child was paused after step killed_after - 1, so no step is in flight: the file must be exact
    assert done == killed_after, (
        f"the child reported {done} committed steps, expected {killed_after}"
    )
    set_env(monkeypatch, db)
    recovered_client = TestClient(app_from_environment())
    assert recovered_client.get("/health/ready").status_code == 200
    recovered_client.close()
    assert snapshot(db) == fresh_prefix(tmp_path, monkeypatch, done)
