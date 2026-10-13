"""Startup and fail-closed readiness (INV-18, NFR-02, SEC-10, TEST-18, TEST-30 direct-corruption half)."""

from __future__ import annotations

import os
import pathlib
import sqlite3
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from abm.application.caller import CallerContext
from abm.application.closure import close_account
from abm.application.registration import register_account
from abm.domain.results import Success
from abm.persistence.database import DatabaseUnavailable, open_database
from abm.persistence.migrations import (
    Migration,
    MigrationError,
    apply_migrations,
    checksum,
    load_migrations,
)
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
    ).fetchall() == [(m.version,) for m in MIGRATIONS]
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
            f"INSERT INTO schema_version VALUES ({len(MIGRATIONS) + 1}, '{len(MIGRATIONS) + 1:04d}_future', ?, ?)",
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
    try:
        for sql, params in statements:
            conn.execute(sql, params)
    finally:
        conn.execute("PRAGMA ignore_check_constraints = OFF")
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
            "hold-only rejection recorded as a ledger entry (specs/05 s5)",
            [
                (MOVEMENT, ("m1", "outgoing_ach", "rejected", NOW, NOW)),
                (
                    (
                        "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind,"
                        " occurred_at) VALUES ('e1', 'm1', 'rejection', ?)"
                    ),
                    (NOW,),
                ),
                (
                    (
                        "INSERT INTO holds (hold_id, movement_id, account_id, amount_cents, state,"
                        " evidence_reference, created_at, finalized_at) VALUES ('h1', 'm1', 'acct-1', 500,"
                        " 'released', 'e1', ?, ?)"
                    ),
                    (NOW, NOW),
                ),
                (
                    (
                        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind,"
                        " direction, amount_cents, authorized_caller_id, authorized_role, created_at)"
                        " VALUES ('l1', 'acct-1', 'm1', 'outgoing_settlement', 'debit', 500, 'c', 'r', ?)"
                    ),
                    (NOW,),
                ),
                ("UPDATE accounts SET current_balance_cents = -500", ()),
            ],
            [INTEGRITY_FAILED],
        ),
        (
            "finalized hold citing evidence of another movement (specs/05 s5)",
            [
                (MOVEMENT, ("m1", "card", "cleared", NOW, NOW)),
                (MOVEMENT, ("m2", "card", "cleared", NOW, NOW)),
                (
                    (
                        "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind,"
                        " occurred_at) VALUES ('e2', 'm2', 'clearing', ?)"
                    ),
                    (NOW,),
                ),
                (
                    (
                        "INSERT INTO holds (hold_id, movement_id, account_id, amount_cents, state,"
                        " evidence_reference, created_at, finalized_at) VALUES ('h1', 'm1', 'acct-1', 500,"
                        " 'posted', 'e2', ?, ?)"
                    ),
                    (NOW, NOW),
                ),
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
        (
            "stored idempotency response that is not valid JSON (specs/05 s7)",
            [
                ("PRAGMA ignore_check_constraints = ON", ()),
                (
                    (
                        "INSERT INTO idempotency_outcomes (scope, idempotency_key, fingerprint,"
                        " instruction_id, outcome_class, http_status, response_json, created_at)"
                        " VALUES ('bad-json', 'k', ?, 'i', 'success', 200, '{not json', ?)"
                    ),
                    ("f" * 64, NOW),
                ),
            ],
            [INTEGRITY_FAILED],
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


def test_readiness_on_a_live_connection_reports_a_newer_schema_as_unsupported(
    path: pathlib.Path,
) -> None:
    conn = start_database(path, MIGRATIONS, NOW).connection
    assert conn is not None
    assert reasons(conn) == []
    conn.execute(
        f"INSERT INTO schema_version VALUES ({len(MIGRATIONS) + 1}, '{len(MIGRATIONS) + 1:04d}_future', ?, ?)",
        ("a" * 64, NOW),
    )
    assert reasons(conn) == [SCHEMA_UNSUPPORTED]


def register_second_account(conn: sqlite3.Connection) -> None:
    clock = ControllableClock(datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC))
    body = {
        "instruction_id": "ins-2",
        "account_id": "acct-2",
        "customer_id": "cust-2",
        "currency": "USD",
        "eligibility_reference": "elig-2",
    }
    caller = CallerContext("registrar-1", "account_registrar", "corr-2")
    result = register_account(SqliteUnitOfWork(conn), clock, caller, "key-2", body)
    assert isinstance(result, Success)


def test_a_hold_reserving_another_accounts_movement_is_integrity_failed(
    path: pathlib.Path,
) -> None:
    conn = registered(path)
    register_second_account(conn)
    assert reasons(conn) == []
    tamper(
        conn,
        [
            (MOVEMENT, ("m1", "outgoing_ach", "accepted_with_hold", NOW, NOW)),
            (
                (
                    "INSERT INTO holds (hold_id, movement_id, account_id, amount_cents, state,"
                    " created_at) VALUES ('h1', 'm1', 'acct-2', 500, 'active', ?)"
                ),
                (NOW,),
            ),
        ],
    )
    assert reasons(conn) == [INTEGRITY_FAILED]


def test_a_non_retained_table_definition_changed_out_of_band_is_integrity_failed(
    path: pathlib.Path,
) -> None:
    registered(path).close()
    conn = open_database(path)
    conn.execute("PRAGMA writable_schema = ON")
    conn.execute(
        "UPDATE sqlite_master SET sql = replace(sql, 'CHECK (state IN (''pending'','"
        ", 'CHECK (1 OR state IN (''pending'',') WHERE type = 'table' AND name = 'movements'"
    )
    conn.execute("PRAGMA writable_schema = OFF")
    conn.close()
    result = start_database(path, MIGRATIONS, NOW)
    assert result.reasons == (INTEGRITY_FAILED,) and result.connection is None


class _CodedError(sqlite3.OperationalError):
    """A driver error carrying a SQLite primary result code, as sqlite3 raises it."""

    def __init__(self, code: int) -> None:
        super().__init__("simulated storage error")
        self.sqlite_errorcode = code


# (SQLite primary code, documented reason): busy, I/O error, corrupt, full, read-only, cannot-open,
# not-a-database, and any other code
STORAGE_CLASSES = [
    (5, DATABASE_BUSY),
    (6, DATABASE_BUSY),
    (10, INTEGRITY_FAILED),
    (11, INTEGRITY_FAILED),
    (13, INTEGRITY_FAILED),
    (8, DATABASE_UNAVAILABLE),
    (14, DATABASE_UNAVAILABLE),
    (26, DATABASE_UNAVAILABLE),
    (1, DATABASE_UNAVAILABLE),
]


@pytest.mark.parametrize(("code", "expected"), STORAGE_CLASSES)
def test_each_storage_error_class_maps_to_the_documented_reason_on_readiness(
    path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, code: int, expected: str
) -> None:
    conn = registered(path)

    def fail(_conn: sqlite3.Connection) -> bool:
        raise _CodedError(code)

    monkeypatch.setattr("abm.persistence.readiness._can_begin_write", fail)
    assert reasons(conn) == [expected]


@pytest.mark.parametrize(("code", "expected"), STORAGE_CLASSES)
def test_each_storage_error_class_maps_to_the_documented_reason_at_startup(
    path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, code: int, expected: str
) -> None:
    def fail(conn: sqlite3.Connection, migrations: object, applied_at: str) -> None:
        raise MigrationError("MIGRATION_FAILED") from _CodedError(code)

    monkeypatch.setattr("abm.persistence.readiness.apply_migrations", fail)
    result = start_database(path, MIGRATIONS, NOW)
    assert result.reasons == (expected,) and result.connection is None


def test_a_corrupt_database_file_at_startup_is_integrity_failed(
    path: pathlib.Path,
) -> None:
    ready = start_database(path, MIGRATIONS, NOW).connection
    assert ready is not None
    ready.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    ready.close()
    data = bytearray(path.read_bytes())
    for offset in range(4096, len(data), 4096):  # damage every page after the first
        data[offset + 100 : offset + 400] = b"\x07" * 300
    path.write_bytes(bytes(data))
    result = start_database(path, MIGRATIONS, NOW)
    assert result.reasons == (INTEGRITY_FAILED,) and result.connection is None


def test_an_additive_upgrade_from_an_older_schema_is_ready(path: pathlib.Path) -> None:
    conn = open_database(path)
    apply_migrations(
        conn, MIGRATIONS[:1], NOW
    )  # an older release applied only the first migration
    conn.close()
    upgraded = start_database(path, MIGRATIONS, "2026-10-10T00:00:00Z")
    assert upgraded.ready and upgraded.reasons == ()
    assert upgraded.connection is not None
    assert upgraded.connection.execute(
        "SELECT version FROM schema_version"
    ).fetchall() == [(m.version,) for m in MIGRATIONS]


@pytest.mark.parametrize(("code", "expected"), STORAGE_CLASSES)
def test_each_storage_error_class_maps_to_the_documented_reason_at_the_open_step(
    path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, code: int, expected: str
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise DatabaseUnavailable("simulated") from _CodedError(code)

    monkeypatch.setattr("abm.persistence.readiness.open_database", fail)
    result = start_database(path, MIGRATIONS, NOW)
    assert result.reasons == (expected,) and result.connection is None


class _FailingExecute:
    """Delegates to a real connection, but raises the given error for statements starting with marker."""

    def __init__(self, conn: sqlite3.Connection, marker: str, error: Exception) -> None:
        self._conn, self._marker, self._error = conn, marker, error

    def execute(self, sql: str, params: object = ()) -> sqlite3.Cursor:
        if sql.startswith(self._marker):
            raise self._error
        return self._conn.execute(sql, cast(Any, params))


@pytest.mark.parametrize(("code", "expected"), STORAGE_CLASSES)
def test_each_storage_error_class_maps_to_the_documented_reason_at_the_integrity_check(
    path: pathlib.Path, code: int, expected: str
) -> None:
    conn = registered(path)
    failing = _FailingExecute(conn, "PRAGMA integrity_check", _CodedError(code))
    assert readiness_reasons(cast(sqlite3.Connection, failing), MIGRATIONS) == [
        expected
    ]


def test_an_unexpected_migration_failure_is_a_controlled_result(
    path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_conn: sqlite3.Connection, _migrations: object, _applied_at: str) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr("abm.persistence.readiness.apply_migrations", fail)
    result = start_database(path, MIGRATIONS, NOW)
    assert result.reasons == (DATABASE_UNAVAILABLE,) and result.connection is None


def test_a_read_only_parent_is_unavailable_before_the_database_is_opened(
    path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_access = os.access

    def parent_is_read_only(target: object, mode: int) -> bool:
        if pathlib.Path(str(target)) == path.parent:
            return False
        return real_access(target, mode)  # type: ignore[arg-type]

    monkeypatch.setattr("abm.persistence.readiness.os.access", parent_is_read_only)
    result = start_database(path, MIGRATIONS, NOW)
    assert result.reasons == (DATABASE_UNAVAILABLE,) and result.connection is None
    assert not path.exists()  # the check ran before any file was created


def test_a_late_clearing_after_an_expired_hold_is_ready(path: pathlib.Path) -> None:
    conn = registered(path)
    tamper(
        conn,
        [
            (MOVEMENT, ("m1", "card", "late_cleared", NOW, NOW)),
            (
                (
                    "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind,"
                    " occurred_at) VALUES ('e1', 'm1', 'expiration', ?)"
                ),
                (NOW,),
            ),
            (
                (
                    "INSERT INTO holds (hold_id, movement_id, account_id, amount_cents, state,"
                    " evidence_reference, created_at, finalized_at) VALUES ('h1', 'm1', 'acct-1', 500,"
                    " 'released', 'e1', ?, ?)"
                ),
                (NOW, NOW),
            ),
            (
                (
                    "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind,"
                    " direction, amount_cents, authorized_caller_id, authorized_role, created_at)"
                    " VALUES ('l1', 'acct-1', 'm1', 'card_clearing', 'debit', 500, 'c', 'r', ?)"
                ),
                (NOW,),
            ),
            ("UPDATE accounts SET current_balance_cents = -500", ()),
        ],
    )
    assert (
        reasons(conn) == []
    )  # permitted late evidence (INV-16) is not a finalized-state violation


def test_section_5_effect_and_evidence_rules_are_refused_by_the_schema(
    path: pathlib.Path,
) -> None:
    """specs/05 s5 is enforced by UNIQUE and CHECK constraints, so readiness does not repeat them."""
    conn = registered(path)
    conn.execute(MOVEMENT, ("m5", "incoming_ach", "settled", NOW, NOW))
    entry = (
        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind, direction,"
        " amount_cents, authorized_caller_id, authorized_role, created_at)"
        " VALUES (?, 'acct-1', 'm5', ?, ?, 500, 'c', 'r', ?)"
    )
    conn.execute(entry, ("l5a", "incoming_settlement", "credit", NOW))
    refused = [
        (
            "second effect of the same kind on one movement",
            ("l5b", "incoming_settlement", "credit", NOW),
        ),
        (
            "effect kind with the wrong direction",
            ("l5c", "incoming_settlement", "debit", NOW),
        ),
        ("effect kind outside the allowlist", ("l5d", "hold_release", "credit", NOW)),
    ]
    for label, params in refused:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(entry, params)
        assert conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0] == 1, (
            label
        )
    evidence = (
        "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind, occurred_at)"
        " VALUES ('e5', 'm5', ?, ?)"
    )
    conn.execute(evidence, ("settlement", NOW))
    with pytest.raises(sqlite3.IntegrityError):  # an evidence reference is unique
        conn.execute(evidence, ("rejection", NOW))


CLOSER = CallerContext("registrar-1", "account_registrar", "corr-2")


def closed_by_command(conn: sqlite3.Connection) -> None:
    """Close acct-1 through the real closure command, at the same second as registration."""
    clock = ControllableClock(datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC))
    result = close_account(
        SqliteUnitOfWork(conn),
        clock,
        CLOSER,
        "key-close",
        "acct-1",
        {"instruction_id": "ins-close"},
    )
    assert isinstance(result, Success)


def ledger_effect(
    entry: str,
    instruction: str,
    movement_type: str,
    state: str,
    effect: str,
    direction: str,
) -> list[tuple[str, tuple[object, ...]]]:
    """A ledger entry with its movement, its successful trace and outcome, and the projection it moves."""
    delta = 500 if direction == "credit" else -500
    return [
        (MOVEMENT, ("m-late", movement_type, state, NOW, NOW)),
        (
            (
                "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind, direction,"
                " amount_cents, authorized_caller_id, authorized_role, created_at)"
                " VALUES (?, 'acct-1', 'm-late', ?, ?, 500, 'c', 'r', ?)"
            ),
            (entry, effect, direction, NOW),
        ),
        (
            (
                "INSERT INTO idempotency_outcomes (scope, idempotency_key, fingerprint, instruction_id,"
                " outcome_class, http_status, response_json, created_at)"
                " VALUES (?, 'k', ?, ?, 'success', 200, '{\"ok\":true}', ?)"
            ),
            (f"scope-{instruction}", "f" * 64, instruction, NOW),
        ),
        (
            (
                "INSERT INTO audit_trace (instruction_id, account_id, movement_id, ledger_entry_id,"
                " movement_state, operation, outcome, caller_id, caller_role, correlation_id, occurred_at)"
                " VALUES (?, 'acct-1', 'm-late', ?, ?, 'post', 'accepted', 'c', 'r', 'corr', ?)"
            ),
            (instruction, entry, state, NOW),
        ),
        (
            "UPDATE accounts SET current_balance_cents = current_balance_cents + ?",
            (delta,),
        ),
    ]


def test_a_same_second_forbidden_effect_after_closure_is_integrity_failed(
    path: pathlib.Path,
) -> None:
    """Same second as closed_at: only the trace sequence orders it after the closure (specs/05 s7, INV-16)."""
    conn = registered(path)
    closed_by_command(conn)
    assert reasons(conn) == []
    tamper(
        conn,
        ledger_effect(
            "l-late",
            "ins-late",
            "incoming_ach",
            "settled",
            "incoming_settlement",
            "credit",
        ),
    )
    assert reasons(conn) == [INTEGRITY_FAILED]


def test_a_permitted_late_clearing_in_the_closure_second_stays_ready(
    path: pathlib.Path,
) -> None:
    conn = registered(path)
    closed_by_command(conn)
    tamper(
        conn,
        ledger_effect(
            "l-late", "ins-late", "card", "late_cleared", "card_clearing", "debit"
        ),
    )
    assert reasons(conn) == []


def test_a_forbidden_effect_recorded_before_closure_in_the_same_second_stays_ready(
    path: pathlib.Path,
) -> None:
    conn = registered(path)
    tamper(
        conn,
        ledger_effect(
            "l-pre",
            "ins-pre",
            "incoming_ach",
            "settled",
            "incoming_settlement",
            "credit",
        )
        + [
            (
                "UPDATE accounts SET status = 'closed', closed_at = ?",
                (NOW,),
            ),
            (
                (
                    "INSERT INTO idempotency_outcomes (scope, idempotency_key, fingerprint, instruction_id,"
                    " outcome_class, http_status, response_json, created_at)"
                    " VALUES ('scope-close', 'k', ?, 'ins-close', 'success', 200, '{\"ok\":true}', ?)"
                ),
                ("f" * 64, NOW),
            ),
            (
                (
                    "INSERT INTO audit_trace (instruction_id, account_id, operation, outcome, caller_id,"
                    " caller_role, correlation_id, occurred_at)"
                    " VALUES ('ins-close', 'acct-1', 'close_account', 'accepted', 'registrar-1',"
                    " 'account_registrar', 'corr-2', ?)"
                ),
                (NOW,),
            ),
        ],
    )
    assert reasons(conn) == []
