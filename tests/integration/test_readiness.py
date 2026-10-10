"""Startup and fail-closed readiness (INV-18, NFR-02, SEC-10, TEST-18, TEST-30 direct-corruption half)."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest

from abm.application.caller import CallerContext
from abm.application.registration import register_account
from abm.domain.results import Success
from abm.persistence.database import open_database
from abm.persistence.migrations import Migration, checksum, load_migrations
from abm.persistence.readiness import (
    DATABASE_BUSY,
    DATABASE_UNAVAILABLE,
    FOREIGN_KEY_FAILED,
    INTEGRITY_FAILED,
    SCHEMA_UNSUPPORTED,
    readiness_reasons,
    start_database,
)
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = load_migrations(ROOT / "migrations")
NOW = "2026-10-09T12:00:00Z"
ALLOWED_REASONS = {
    DATABASE_BUSY,
    DATABASE_UNAVAILABLE,
    FOREIGN_KEY_FAILED,
    INTEGRITY_FAILED,
    SCHEMA_UNSUPPORTED,
}


@pytest.fixture
def path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "abm.sqlite3"


def registered(path: pathlib.Path) -> sqlite3.Connection:
    """A ready database holding one properly registered account."""
    started = start_database(path, MIGRATIONS, NOW)
    assert started.connection is not None
    clock = ControllableClock(datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC))
    body = {
        "instruction_id": "ins-1",
        "account_id": "acct-1",
        "customer_id": "cust-1",
        "currency": "USD",
        "eligibility_reference": "elig-1",
    }
    caller = CallerContext("registrar-1", "account_registrar", "corr-1")
    result = register_account(
        SqliteUnitOfWork(started.connection), clock, caller, "key-1", body
    )
    assert isinstance(result, Success)
    return started.connection


def reasons(conn: sqlite3.Connection) -> list[str]:
    return readiness_reasons(conn, MIGRATIONS)


def drop_guards(conn: sqlite3.Connection) -> None:
    """Simulate direct database tampering that bypasses the application's immutability triggers."""
    names = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    ]
    for name in names:
        conn.execute(f"DROP TRIGGER {name}")


def test_empty_volume_starts_ready_and_records_the_schema_version(
    path: pathlib.Path,
) -> None:
    started = start_database(path, MIGRATIONS, NOW)
    assert started.ready and started.reasons == ()
    assert started.connection is not None
    assert started.connection.execute(
        "SELECT version FROM schema_version"
    ).fetchall() == [(1,)]
    assert started.connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_restart_on_the_intact_volume_stays_ready_with_state_preserved(
    path: pathlib.Path,
) -> None:
    first = registered(path)
    first.close()
    again = start_database(path, MIGRATIONS, "2026-10-10T00:00:00Z")
    assert again.ready and again.connection is not None
    assert again.connection.execute("SELECT account_id FROM accounts").fetchall() == [
        ("acct-1",)
    ]
    stamp = again.connection.execute("SELECT applied_at FROM schema_version").fetchone()
    assert stamp == (NOW,)  # migrations were not re-applied


def test_a_consistent_database_with_activity_is_ready(path: pathlib.Path) -> None:
    assert reasons(registered(path)) == []


@pytest.mark.parametrize("bad", ["newer", "foreign", "edited"])
def test_unsupported_schema_is_never_ready_and_leaves_no_connection(
    path: pathlib.Path, bad: str
) -> None:
    conn = start_database(path, MIGRATIONS, NOW).connection
    assert conn is not None
    known = list(MIGRATIONS)
    if bad == "newer":
        conn.execute(
            "INSERT INTO schema_version VALUES (2, '0002_future', ?, ?)",
            ("a" * 64, NOW),
        )
    elif bad == "edited":
        known = [Migration(1, "0001_initial", "SELECT 1;", checksum("SELECT 1;"))]
    conn.close()
    if bad == "foreign":
        path.unlink()
        foreign = sqlite3.connect(path)
        foreign.execute("CREATE TABLE somebody_elses (id INTEGER)")
        foreign.commit()
        foreign.close()
    result = start_database(path, known, NOW)
    assert not result.ready and result.connection is None
    assert result.reasons == (SCHEMA_UNSUPPORTED,)


def test_garbage_and_unopenable_files_report_database_unavailable(
    path: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    path.write_bytes(b"this is not a sqlite database at all" * 50)
    assert start_database(path, MIGRATIONS, NOW).reasons == (DATABASE_UNAVAILABLE,)
    assert start_database(
        tmp_path / "missing-dir" / "x.sqlite3", MIGRATIONS, NOW
    ).reasons == (DATABASE_UNAVAILABLE,)
    assert start_database(tmp_path, MIGRATIONS, NOW).reasons == (DATABASE_UNAVAILABLE,)


def test_a_busy_database_reports_database_busy_without_changing_it(
    path: pathlib.Path,
) -> None:
    ready = start_database(path, MIGRATIONS, NOW).connection
    assert ready is not None
    ready.execute("BEGIN IMMEDIATE")  # another writer holds the lock
    blocked = start_database(path, MIGRATIONS, NOW, busy_timeout_ms=50)
    assert blocked.reasons == (DATABASE_BUSY,) and blocked.connection is None
    ready.execute("ROLLBACK")
    assert start_database(path, MIGRATIONS, NOW).ready  # recovers once the lock is gone


def test_readiness_reports_busy_for_an_already_open_connection(
    path: pathlib.Path,
) -> None:
    ready = start_database(path, MIGRATIONS, NOW, busy_timeout_ms=50).connection
    assert ready is not None
    other = open_database(path, busy_timeout_ms=50)
    other.execute("BEGIN IMMEDIATE")
    assert reasons(ready) == [DATABASE_BUSY]
    other.execute("ROLLBACK")
    assert reasons(ready) == []


def tamper(
    conn: sqlite3.Connection, statements: list[tuple[str, tuple[object, ...]]]
) -> None:
    """Write bad rows past the guards, then restore the guards, so only the data checks are tested."""
    saved = [
        r[0]
        for r in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger'")
    ]
    drop_guards(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    for sql, params in statements:
        conn.execute(sql, params)
    for sql in saved:
        conn.execute(sql)


MOVEMENT = (
    "INSERT INTO movements (movement_id, account_id, movement_type, state, amount_cents,"
    " currency, created_at, updated_at) VALUES (?, 'acct-1', ?, ?, 500, 'USD', ?, ?)"
)
HOLD = (
    "INSERT INTO holds (hold_id, movement_id, account_id, amount_cents, state, created_at)"
    " VALUES (?, ?, 'acct-1', 500, 'active', ?)"
)


@pytest.mark.parametrize(
    ("label", "statements", "expected"),
    [
        (
            "projection differs from the ledger",
            [("UPDATE accounts SET current_balance_cents = 5", ())],
            [INTEGRITY_FAILED],
        ),
        (
            "ledger entry without a matching projection",
            [
                (MOVEMENT, ("m1", "incoming_ach", "settled", NOW, NOW)),
                (
                    (
                        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind,"
                        " direction, amount_cents, authorized_caller_id, authorized_role, created_at)"
                        " VALUES ('l1', 'acct-1', 'm1', 'incoming_settlement', 'credit', 500, 'c', 'r', ?)"
                    ),
                    (NOW,),
                ),
            ],
            [INTEGRITY_FAILED],
        ),
        (
            "account without its registration trace",
            [("DELETE FROM audit_trace", ())],
            [INTEGRITY_FAILED],
        ),
        (
            "account without its retention row",
            [("DELETE FROM retention_metadata", ())],
            [INTEGRITY_FAILED],
        ),
        (
            "accepted trace without its successful outcome",
            [("DELETE FROM idempotency_outcomes", ())],
            [INTEGRITY_FAILED],
        ),
        (
            "active hold on a settled movement",
            [
                (MOVEMENT, ("m1", "outgoing_ach", "settled", NOW, NOW)),
                (HOLD, ("h1", "m1", NOW)),
            ],
            [INTEGRITY_FAILED],
        ),
        (
            "movement that needs a hold has none",
            [(MOVEMENT, ("m1", "card", "authorized_with_hold", NOW, NOW))],
            [INTEGRITY_FAILED],
        ),
        (
            "transfer with unequal sides",
            [
                (MOVEMENT, ("m1", "internal_transfer", "completed", NOW, NOW)),
                (
                    (
                        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind,"
                        " direction, amount_cents, authorized_caller_id, authorized_role, created_at)"
                        " VALUES ('l1', 'acct-1', 'm1', 'transfer_source_debit', 'debit', 500, 'c', 'r', ?)"
                    ),
                    (NOW,),
                ),
                ("UPDATE accounts SET current_balance_cents = -500", ()),
            ],
            [INTEGRITY_FAILED],
        ),
        (
            "closed account with an active hold",
            [
                (MOVEMENT, ("m1", "card", "authorized_with_hold", NOW, NOW)),
                (HOLD, ("h1", "m1", NOW)),
                ("UPDATE accounts SET status = 'closed', closed_at = ?", (NOW,)),
            ],
            [INTEGRITY_FAILED],
        ),
        (
            "row referencing a missing account",
            [
                (
                    (
                        "INSERT INTO movements (movement_id, account_id, movement_type, state,"
                        " amount_cents, currency, created_at, updated_at)"
                        " VALUES ('m9', 'ghost', 'card', 'cleared', 500, 'USD', ?, ?)"
                    ),
                    (NOW, NOW),
                )
            ],
            [FOREIGN_KEY_FAILED],
        ),
    ],
)
def test_direct_corruption_makes_readiness_fail_with_a_safe_code(
    path: pathlib.Path,
    label: str,
    statements: list[tuple[str, tuple[object, ...]]],
    expected: list[str],
) -> None:
    conn = registered(path)
    assert reasons(conn) == []
    tamper(conn, statements)
    assert reasons(conn) == expected, label


def test_file_level_corruption_is_detected_and_never_repaired(
    path: pathlib.Path,
) -> None:
    conn = registered(path)
    conn.execute("BEGIN IMMEDIATE")
    for i in range(300):  # enough pages that damage lands inside the data
        conn.execute(
            "INSERT INTO idempotency_outcomes (scope, idempotency_key, fingerprint, instruction_id,"
            " outcome_class, http_status, response_json, created_at)"
            " VALUES (?, 'k', ?, 'i', 'success', 200, '{\"ok\":true}', ?)",
            (f"scope-{i}", "f" * 64, NOW),
        )
    conn.execute("COMMIT")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    data = bytearray(path.read_bytes())
    for offset in range(4096 * 3, 4096 * 3 + 600):
        data[offset] = 0xFF
    path.write_bytes(bytes(data))
    result = start_database(path, MIGRATIONS, NOW)
    assert not result.ready and result.connection is None
    assert result.reasons and set(result.reasons) <= ALLOWED_REASONS
    assert (
        path.read_bytes()[4096 * 3 : 4096 * 3 + 600] == b"\xff" * 600
    )  # no repair attempted


def test_readiness_checks_write_nothing(path: pathlib.Path) -> None:
    conn = registered(path)
    tamper(conn, [("UPDATE accounts SET current_balance_cents = 5", ())])
    before = list(conn.iterdump())
    assert reasons(conn) == [INTEGRITY_FAILED]
    assert (
        list(conn.iterdump()) == before
    )  # the inconsistency is reported, not repaired


def test_reason_codes_are_controlled_values_only(path: pathlib.Path) -> None:
    conn = registered(path)
    tamper(
        conn,
        [
            ("UPDATE accounts SET current_balance_cents = 5", ()),
            ("DELETE FROM retention_metadata", ()),
        ],
    )
    found = reasons(conn)
    assert found and set(found) <= ALLOWED_REASONS


def test_a_guard_trigger_removed_outside_the_runner_is_not_ready(
    path: pathlib.Path,
) -> None:
    started = start_database(path, MIGRATIONS, NOW)
    assert started.connection is not None
    assert readiness_reasons(started.connection, MIGRATIONS) == []
    started.connection.execute(
        "DROP TRIGGER ledger_entries_no_update"
    )  # bypasses the runner
    assert readiness_reasons(started.connection, MIGRATIONS) == [INTEGRITY_FAILED]


def test_a_missing_table_is_integrity_failed_not_database_unavailable(
    path: pathlib.Path,
) -> None:
    conn = registered(path)
    conn.execute("ALTER TABLE ledger_entries RENAME TO ledger_old")
    assert readiness_reasons(conn, MIGRATIONS) == [INTEGRITY_FAILED]


def test_a_dropped_index_is_integrity_failed(path: pathlib.Path) -> None:
    conn = registered(path)
    conn.execute("DROP INDEX idx_ledger_account_sequence")
    assert readiness_reasons(conn, MIGRATIONS) == [INTEGRITY_FAILED]


def test_a_temp_object_on_the_checked_connection_is_integrity_failed(
    path: pathlib.Path,
) -> None:
    conn = registered(path)
    conn.execute(
        "CREATE TEMP VIEW shadow_probe AS SELECT 1 AS x"
    )  # invisible to the main object set
    assert readiness_reasons(conn, MIGRATIONS) == [INTEGRITY_FAILED]
