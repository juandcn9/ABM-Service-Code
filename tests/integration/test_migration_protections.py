"""A migration is reviewed text, but the runner must not trust it with retained history or the
shared connection (BT-05, DEC-0002, DEC-0007; specs/07 section 6: destructive migration is a
governance escalation). Prevent with an allowlist authorizer, verify before COMMIT, detect later."""

from __future__ import annotations

import pathlib
import re
import sqlite3

import pytest

import abm.persistence.migrations as migrations_module
from abm.persistence.migrations import (
    PROTECTED_TABLES,
    PROTECTED_TRIGGERS,
    Migration,
    MigrationError,
    apply_migrations,
    checksum,
    load_migrations,
    retained_history_protected,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = load_migrations(ROOT / "migrations")
NOW = "2026-10-09T12:00:00Z"


def migrated(tmp_path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "m.sqlite3", isolation_level=None, timeout=5)
    apply_migrations(conn, BASE, NOW)
    return conn


def second(sql: str) -> Migration:
    return Migration(2, "0002_test", sql, checksum(sql))


def state(conn: sqlite3.Connection) -> list[str]:
    return [*conn.iterdump(), *map(str, conn.execute("PRAGMA integrity_check"))]


ATTACKS = [
    # erase protections or history
    "DROP TRIGGER schema_version_no_delete;\nDELETE FROM schema_version;",
    "DROP TRIGGER IF EXISTS ledger_entries_no_update;",
    'DROP TRIGGER "audit_trace_no_delete";',
    "DROP TRIGGER AUDIT_TRACE_NO_UPDATE;",
    "DELETE FROM schema_version;",
    "UPDATE schema_version SET checksum = 'x';",
    "DELETE FROM ledger_entries;",
    "UPDATE ledger_entries SET amount_cents = 1;",
    "DELETE FROM audit_trace;",
    "UPDATE movement_evidence SET evidence_kind = 'return';",
    "DELETE FROM idempotency_outcomes;",
    "UPDATE idempotency_outcomes SET http_status = 500;",
    "DROP TABLE ledger_entries;",
    "DROP TABLE schema_version;",
    'DROP TABLE "Audit_Trace";',
    "DROP TABLE LEDGER_ENTRIES;",
    "ALTER TABLE ledger_entries RENAME TO old_ledger;",
    "ALTER TABLE audit_trace ADD COLUMN extra TEXT;",
    "CREATE TEMP TABLE ledger_entries (x);",
    # change connection behavior that would outlive the migration
    "PRAGMA ignore_check_constraints = ON;",
    "PRAGMA recursive_triggers = ON;",
    "PRAGMA trusted_schema = ON;",
    "PRAGMA query_only = ON;",
    "PRAGMA locking_mode = EXCLUSIVE;",
    "PRAGMA synchronous = OFF;",
    "PRAGMA journal_mode = DELETE;",
    "PRAGMA writable_schema = ON;",
    "PRAGMA user_version = 7;",
    "PRAGMA schema_version = 99;",
    "PRAGMA defer_foreign_keys = ON;",
    # transaction and database escape
    "ROLLBACK;",
    "COMMIT;",
    "SAVEPOINT s;",
    "ATTACH DATABASE ':memory:' AS other;",
    # a new trigger that reaches into retained history
    "CREATE TABLE note (x);\nCREATE TRIGGER evil AFTER INSERT ON note\nBEGIN DELETE FROM ledger_entries; END;",
    "CREATE TABLE note (x);\nCREATE TRIGGER evil AFTER INSERT ON note\nBEGIN UPDATE audit_trace SET operation = 'x'; END;",
]


@pytest.mark.parametrize("attack", ATTACKS)
def test_attacks_on_retained_history_or_the_connection_are_refused_with_nothing_changed(
    tmp_path: pathlib.Path, attack: str
) -> None:
    conn = migrated(tmp_path)
    before = state(conn)
    settings = [
        conn.execute(f"PRAGMA {p}").fetchone()[0]
        for p in ("query_only", "recursive_triggers", "trusted_schema")
    ]
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [*BASE, second(attack)], NOW)
    assert excinfo.value.code in {"MIGRATION_FAILED", "MIGRATION_FILES_INVALID"}
    assert not conn.in_transaction
    assert state(conn) == before
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone() == (1,)
    after = [
        conn.execute(f"PRAGMA {p}").fetchone()[0]
        for p in ("query_only", "recursive_triggers", "trusted_schema")
    ]
    assert after == settings  # no setting was left changed on the shared connection
    assert retained_history_protected(conn)


# Transaction control ends the transaction before any verification could run, so it is stopped
# only by the load-time check and the authorizer (two layers, each tested above).
VERIFIABLE = [a for a in ATTACKS if not a.startswith(("ROLLBACK", "COMMIT"))]


@pytest.mark.parametrize("attack", VERIFIABLE)
def test_the_post_migration_verification_catches_what_the_authorizer_would_miss(
    tmp_path: pathlib.Path, attack: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second, independent layer: even with a permissive authorizer, damage cannot be committed."""
    monkeypatch.setattr(
        migrations_module, "_migration_authorizer", lambda *_args: sqlite3.SQLITE_OK
    )
    conn = migrated(tmp_path)
    before = state(conn)
    try:
        apply_migrations(conn, [*BASE, second(attack)], NOW)
    except MigrationError:
        pass  # refused: the database must be exactly as before
    else:
        # accepted only if the statement was harmless to the guarantees; then they all still hold
        assert retained_history_protected(conn)
        assert conn.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ).fetchall()[0] == (1,)
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        return
    assert not conn.in_transaction and state(conn) == before


LEGITIMATE = (
    "ALTER TABLE accounts ADD COLUMN display_note TEXT;\n"
    "CREATE TABLE extra (id INTEGER PRIMARY KEY, label TEXT);\n"
    "CREATE INDEX idx_extra_label ON extra(label);\n"
    "CREATE VIEW extra_labels AS SELECT label FROM extra;\n"
    "CREATE TRIGGER extra_no_delete BEFORE DELETE ON extra\n"
    "BEGIN SELECT RAISE(ABORT, 'extra rows are kept'); END;\n"
    "INSERT INTO extra (label) VALUES ('seed -- not a comment');\n"
    "INSERT INTO idempotency_outcomes (scope, idempotency_key, fingerprint, instruction_id,"
    " outcome_class, http_status, response_json, created_at)"
    " VALUES ('s', 'k', '"
    + "a" * 64
    + "', 'i', 'success', 200, '{\"ok\":true}', '"
    + NOW
    + "');\n"
    "-- finished\n"
)


def test_legitimate_additive_migrations_still_apply_and_leave_history_protected(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    apply_migrations(conn, [*BASE, second(LEGITIMATE)], "2026-10-10T12:00:00Z")
    assert [
        r[:2]
        for r in conn.execute("SELECT version, migration_name FROM schema_version")
    ] == [
        (1, "0001_initial"),
        (2, "0002_test"),
    ]
    assert conn.execute("SELECT label FROM extra").fetchall() == [
        ("seed -- not a comment",)
    ]
    assert retained_history_protected(conn)
    assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    apply_migrations(conn, [*BASE, second(LEGITIMATE)], NOW)  # rerun is a no-op


def test_the_protected_sets_match_the_shipped_schema() -> None:
    sql = BASE[0].sql
    triggers = set(re.findall(r"CREATE TRIGGER (\w+)", sql))
    assert triggers == set(PROTECTED_TRIGGERS)
    guarded = {re.sub(r"_no_(?:update|delete)$", "", name) for name in triggers}
    assert guarded == set(PROTECTED_TABLES) - {"idempotency_outcomes"}
    # idempotency_outcomes has no trigger in the contract; it is still shielded from migrations
    assert "idempotency_outcomes" in PROTECTED_TABLES


def test_retained_history_protection_is_detected_when_tampering_bypasses_the_runner(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    assert retained_history_protected(conn)
    conn.execute("CREATE TABLE note (x)")
    conn.execute(
        "CREATE TRIGGER sneaky AFTER INSERT ON note BEGIN DELETE FROM ledger_entries; END"
    )
    assert not retained_history_protected(conn)
    conn.execute("DROP TRIGGER sneaky")
    assert retained_history_protected(conn)
    conn.execute("DROP TRIGGER ledger_entries_no_delete")
    assert not retained_history_protected(conn)


def test_a_connection_in_a_nonstandard_state_is_not_altered_by_the_runner(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    conn.execute("PRAGMA recursive_triggers = ON")  # the caller's own choice
    apply_migrations(conn, [*BASE, second("CREATE TABLE extra (id INTEGER);")], NOW)
    assert conn.execute("PRAGMA recursive_triggers").fetchone() == (1,)
