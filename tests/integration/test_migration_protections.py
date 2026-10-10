"""A migration is reviewed text, but the runner must not trust it with retained history or the
shared connection (BT-05, DEC-0002, DEC-0007; specs/07 section 6: destructive migration is a
governance escalation). Prevent with an allowlist authorizer, verify before COMMIT, detect later."""

from __future__ import annotations

import dataclasses
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


HEX = "a" * 64

# one row in every retained table, so the attacks run against real history and not an empty schema
SEED = [
    (
        "INSERT INTO accounts (account_id, customer_id, currency, eligibility_reference, status,"
        " current_balance_cents, restriction, created_at)"
        " VALUES ('acc-1', 'cust-1', 'USD', 'elig-1', 'open', 100, 'none', '2026-10-09T10:00:00Z')"
    ),
    (
        "INSERT INTO movements (movement_id, account_id, movement_type, state, amount_cents, currency,"
        " external_reference, created_at, updated_at)"
        " VALUES ('mov-1', 'acc-1', 'incoming_ach', 'settled', 100, 'USD', 'ext-1',"
        " '2026-10-09T10:01:00Z', '2026-10-09T10:01:00Z')"
    ),
    (
        "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind, occurred_at)"
        " VALUES ('ev-1', 'mov-1', 'settlement', '2026-10-09T10:02:00Z')"
    ),
    (
        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind, direction,"
        " amount_cents, authorized_caller_id, authorized_role, created_at)"
        " VALUES ('le-1', 'acc-1', 'mov-1', 'incoming_settlement', 'credit', 100, 'caller', 'role',"
        " '2026-10-09T10:02:00Z')"
    ),
    (
        "INSERT INTO audit_trace (account_id, instruction_id, movement_id, ledger_entry_id,"
        " evidence_reference, movement_state, operation, outcome, caller_id, caller_role,"
        " correlation_id, occurred_at)"
        " VALUES ('acc-1', 'ins-1', 'mov-1', 'le-1', 'ev-1', 'settled', 'incoming_ach_settle',"
        " 'accepted', 'caller', 'role', 'corr-1', '2026-10-09T10:02:00Z')"
    ),
    (
        "INSERT INTO idempotency_outcomes (scope, idempotency_key, fingerprint, instruction_id,"
        " outcome_class, http_status, response_json, created_at)"
        f" VALUES ('acc-1', 'key-1', '{HEX}', 'ins-1', 'success', 200, '{{\"ok\":true}}',"
        " '2026-10-09T10:00:00Z')"
    ),
    "INSERT INTO retention_metadata (account_id, record_id) VALUES ('acc-1', 'acc-1')",
]


def migrated(tmp_path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "m.sqlite3", isolation_level=None, timeout=5)
    apply_migrations(conn, BASE, NOW)
    for statement in SEED:
        conn.execute(statement)
    return conn


def second(sql: str) -> Migration:
    # the next free version after the shipped migrations
    version = len(BASE) + 1
    return Migration(version, f"{version:04d}_test", sql, checksum(sql))


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
    "ALTER TABLE movements DROP COLUMN amount_cents;",
    "ALTER TABLE movements RENAME COLUMN amount_cents TO amount;",
    "ALTER TABLE holds RENAME TO holds_old;",
    "ALTER TABLE audit_trace ADD COLUMN extra TEXT;",
    "CREATE TEMP TABLE ledger_entries (x);",
    # change connection behavior that would outlive the migration
    "PRAGMA ignore_check_constraints = ON;",
    "PRAGMA recursive_triggers = ON;",
    "PRAGMA trusted_schema = OFF;",
    "PRAGMA query_only = ON;",
    "PRAGMA locking_mode = EXCLUSIVE;",
    "PRAGMA synchronous = OFF;",
    "PRAGMA journal_mode = MEMORY;",
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
    # a trigger that names the history table in quotes is still a trigger on a retained table
    (
        "CREATE TABLE note (x);\nCREATE TRIGGER t_quoted AFTER INSERT ON note\nBEGIN"
        " INSERT INTO 'schema_version' (version, migration_name, checksum, applied_at)"
        f" VALUES (9, '0009_forged', '{HEX}', '2026-10-09T10:00:00Z'); END;"
    ),
    "DROP INDEX idx_ledger_account_sequence;",
    # rewrite a retained row in place (REPLACE rewrote rows in the third review's F1)
    (
        "REPLACE INTO ledger_entries (sequence, entry_id, account_id, movement_id, effect_kind,"
        " direction, amount_cents, authorized_caller_id, authorized_role, created_at)"
        " VALUES (1, 'le-1', 'acc-1', 'mov-1', 'incoming_settlement', 'credit', 999, 'c', 'r',"
        " '2026-10-09T10:02:00Z');"
    ),
    (
        "INSERT OR REPLACE INTO audit_trace (sequence, instruction_id, operation, outcome, caller_id,"
        " caller_role, correlation_id, occurred_at)"
        " VALUES (1, 'ins-1', 'forged', 'accepted', 'c', 'r', 'corr', '2026-10-09T10:02:00Z');"
    ),
    (
        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind, direction,"
        " amount_cents, authorized_caller_id, authorized_role, created_at)"
        " VALUES ('le-1', 'acc-1', 'mov-1', 'incoming_settlement', 'credit', 999, 'c', 'r',"
        " '2026-10-09T10:02:00Z') ON CONFLICT (entry_id) DO UPDATE SET amount_cents = 999;"
    ),
    # tamper with AUTOINCREMENT bookkeeping, then append forged history
    "UPDATE sqlite_sequence SET seq = 0 WHERE name = 'ledger_entries';",
    "DELETE FROM sqlite_sequence;",
    "INSERT INTO sqlite_sequence (name, seq) VALUES ('ledger_entries', 0);",
    (
        "INSERT INTO schema_version (version, migration_name, checksum, applied_at)"
        f" VALUES (2, '0002_forged', '{HEX}', '2026-10-09T10:00:00Z');"
    ),
    # a gap-free forged row the runner's own insert cannot collide with (only the history check sees it)
    (
        "INSERT INTO schema_version (version, migration_name, checksum, applied_at)"
        f" VALUES (9, '0009_forged', '{HEX}', '2026-10-09T10:00:00Z');"
    ),
    # shadow retained tables or their guards for this connection only
    "CREATE TEMP VIEW ledger_entries AS SELECT 1 AS entry_id;",
    "CREATE TEMP TRIGGER t_tmp AFTER INSERT ON accounts BEGIN SELECT 1; END;",
    (
        "DROP TRIGGER ledger_entries_no_update;\n"
        "CREATE TRIGGER ledger_entries_no_update BEFORE UPDATE ON ledger_entries"
        " BEGIN SELECT 1; END;"
    ),
    (
        "DROP TRIGGER movement_evidence_no_delete;\n"
        "CREATE TRIGGER movement_evidence_no_delete BEFORE DELETE ON movement_evidence"
        " BEGIN SELECT 1; END;\nDELETE FROM movement_evidence;"
    ),
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
    # only transaction control may be stopped at load time; anything else must reach the runtime layers
    if not attack.startswith(("ROLLBACK", "COMMIT")):
        assert excinfo.value.code == "MIGRATION_FAILED"
    assert not conn.in_transaction
    assert state(conn) == before
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone() == (
        len(BASE),
    )
    after = [
        conn.execute(f"PRAGMA {p}").fetchone()[0]
        for p in ("query_only", "recursive_triggers", "trusted_schema")
    ]
    assert after == settings  # no setting was left changed on the shared connection
    assert retained_history_protected(conn)


# Transaction control ends the transaction before any verification could run, so it is stopped
# only by the load-time check and the authorizer (two layers, each tested above).
VERIFIABLE = [a for a in ATTACKS if not a.startswith(("ROLLBACK", "COMMIT"))]


# SAVEPOINT and ATTACH change no retained state by themselves; PRAGMA synchronous cannot be set
# inside a transaction. The authorizer and verification tests above cover all three.
UNGUARDED_CHECKABLE = [
    a
    for a in VERIFIABLE
    if not a.startswith(("SAVEPOINT", "ATTACH", "PRAGMA synchronous"))
]


@pytest.mark.parametrize("attack", UNGUARDED_CHECKABLE)
def test_each_attack_really_changes_the_database_when_run_unguarded(
    tmp_path: pathlib.Path, attack: str
) -> None:
    """Non-vacuity: a refused attack must do damage when unguarded, not fail as a SQL typo."""
    conn = migrated(tmp_path)
    before = migrations_module._snapshot(conn)
    cookie = conn.execute("PRAGMA schema_version").fetchone()
    refused_by_trigger = False
    conn.execute("BEGIN")
    try:
        for statement in migrations_module._statements(attack):
            try:
                conn.execute(statement)
            except sqlite3.IntegrityError:
                refused_by_trigger = (
                    True  # shipped trigger or CHECK; SQL errors still fail
                )
        try:
            changed = migrations_module._snapshot(conn) != before
        except MigrationError:
            changed = True  # the history can no longer be read: that is damage too
        changed = changed or conn.execute("PRAGMA schema_version").fetchone() != cookie
    finally:
        conn.execute("ROLLBACK")
    assert refused_by_trigger or changed


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
    before_snapshot = migrations_module._snapshot(conn)
    try:
        apply_migrations(conn, [*BASE, second(attack)], NOW)
    except MigrationError:
        pass  # refused: the database must be exactly as before
    else:
        # accepted only if the statement changed nothing retained; then 0002 is simply appended
        after = migrations_module._snapshot(conn)
        assert retained_history_protected(conn)
        assert after.columns == before_snapshot.columns
        assert (after.rows, after.sequences, after.schema, after.temp, after.state) == (
            before_snapshot.rows,
            before_snapshot.sequences,
            before_snapshot.schema,
            before_snapshot.temp,
            before_snapshot.state,
        )
        assert after.history == [
            *[(m.version, m.name, m.checksum) for m in BASE],
            (second(attack).version, second(attack).name, second(attack).checksum),
        ]
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
        *[(m.version, m.name) for m in BASE],
        (len(BASE) + 1, f"{len(BASE) + 1:04d}_test"),
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


# Each rule of the authorizer is checked directly: a retained-table guard is otherwise masked by the
# schema triggers and the verification layer, so an outcome-only test cannot tell the rule is gone.
AUTHORIZER_DECISIONS = [
    (sqlite3.SQLITE_TRANSACTION, None, None, False),
    (sqlite3.SQLITE_SAVEPOINT, "begin", "s", False),
    (sqlite3.SQLITE_ATTACH, "other.sqlite3", "other", False),
    (sqlite3.SQLITE_DETACH, "other", None, False),
    (sqlite3.SQLITE_CREATE_TEMP_TABLE, "t", None, False),
    (sqlite3.SQLITE_CREATE_TEMP_VIEW, "v", None, False),
    (sqlite3.SQLITE_CREATE_TEMP_TRIGGER, "t", "accounts", False),
    (sqlite3.SQLITE_CREATE_TEMP_INDEX, "i", "accounts", False),
    (sqlite3.SQLITE_CREATE_VTABLE, "v", "fts5", False),
    (sqlite3.SQLITE_INSERT, "ledger_entries", None, False),
    (sqlite3.SQLITE_UPDATE, "audit_trace", "operation", False),
    (sqlite3.SQLITE_DELETE, "idempotency_outcomes", None, False),
    (sqlite3.SQLITE_DROP_TABLE, "Ledger_Entries", None, False),
    (sqlite3.SQLITE_INSERT, "sqlite_sequence", None, False),
    (sqlite3.SQLITE_PRAGMA, "writable_schema", None, False),
    (sqlite3.SQLITE_PRAGMA, "foreign_keys", None, True),
    (sqlite3.SQLITE_FUNCTION, None, "load_extension", False),
    (sqlite3.SQLITE_DROP_TRIGGER, "ledger_entries_no_update", "ledger_entries", False),
    (sqlite3.SQLITE_DROP_TRIGGER, "note_trigger", "note", False),
    (sqlite3.SQLITE_ALTER_TABLE, "main", "ledger_entries", False),
    (
        sqlite3.SQLITE_ALTER_TABLE,
        "main",
        "accounts",
        True,
    ),  # additive changes are verified, not refused here
    (sqlite3.SQLITE_UPDATE, "movements", "amount_cents", False),
    (sqlite3.SQLITE_DELETE, "retention_metadata", None, False),
    (sqlite3.SQLITE_DROP_TABLE, "holds", None, False),
    (sqlite3.SQLITE_DROP_INDEX, "idx_holds_account_state", "holds", False),
    (sqlite3.SQLITE_DROP_VIEW, "extra_labels", None, False),
    # non-retained work a migration legitimately needs
    (sqlite3.SQLITE_INSERT, "accounts", None, True),
    (sqlite3.SQLITE_CREATE_TABLE, "note", None, True),
]


@pytest.mark.parametrize(("action", "arg1", "arg2", "allowed"), AUTHORIZER_DECISIONS)
def test_each_authorizer_rule_decides_as_specified(
    action: int, arg1: str | None, arg2: str | None, allowed: bool
) -> None:
    decision = migrations_module._migration_authorizer(action, arg1, arg2, None, None)
    assert (decision == sqlite3.SQLITE_OK) == allowed


def test_a_migration_that_runs_too_long_is_interrupted_and_nothing_changes(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    before = state(conn)
    slow = (
        "CREATE TABLE slow AS WITH RECURSIVE c(x) AS"
        " (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 50000000) SELECT x FROM c;"
    )
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [*BASE, second(slow)], NOW, time_limit_seconds=0.001)
    assert excinfo.value.code == "MIGRATION_FAILED"
    assert not conn.in_transaction
    assert state(conn) == before


def test_a_fast_migration_is_not_interrupted_by_the_time_limit(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    apply_migrations(conn, [*BASE, second(LEGITIMATE)], NOW, time_limit_seconds=600.0)
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone() == (
        len(BASE) + 1,
    )


def test_a_temp_object_or_a_renamed_retained_table_breaks_the_readiness_check(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    conn.execute("CREATE TEMP VIEW ledger_entries AS SELECT 1 AS entry_id")
    assert not retained_history_protected(conn)
    conn.execute("DROP VIEW temp.ledger_entries")
    assert retained_history_protected(conn)
    conn.execute("ALTER TABLE idempotency_outcomes RENAME TO idempotency_old")
    assert not retained_history_protected(conn)


def snapshot(**changes: object) -> migrations_module._Snapshot:
    # history defaults to the expected one, so each case isolates the single clause it targets
    empty = migrations_module._Snapshot(
        rows={},
        sequences={},
        schema=frozenset(),
        temp=frozenset(),
        state=(),
        columns={},
        history=HISTORY,
    )
    return dataclasses.replace(empty, **changes)  # type: ignore[arg-type]


HISTORY = [(m.version, m.name, m.checksum) for m in BASE]
# Verification clauses that a migration cannot reach with the shipped schema (every retained table
# and pinned object already exists after 0001), so they are checked on synthetic snapshots.
PINNED_TABLE_SQL = "CREATE TABLE ledger_entries (x)"
PINNED_TRIGGER_SQL = "CREATE TRIGGER ledger_entries_no_update BEFORE UPDATE ON ledger_entries BEGIN SELECT 1; END"


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            snapshot(history=HISTORY),
            snapshot(history=HISTORY),
            False,
        ),  # control: nothing changed
        (
            snapshot(rows={"ledger_entries": (1, "d")}),
            snapshot(),  # a retained table vanished
            True,
        ),
        (
            snapshot(),
            snapshot(
                rows={"ledger_entries": (1, "d")}
            ),  # a new retained table arrived with rows
            True,
        ),
        (
            snapshot(),
            snapshot(
                schema=frozenset(
                    {("table", "ledger_entries", "ledger_entries", PINNED_TABLE_SQL)}
                )
            ),
            True,  # a pinned table whose text is not the shipped text
        ),
        (
            snapshot(),
            snapshot(
                schema=frozenset(
                    {
                        (
                            "trigger",
                            "ledger_entries_no_update",
                            "ledger_entries",
                            PINNED_TRIGGER_SQL,
                        )
                    }
                )
            ),
            True,  # a pinned trigger whose text is not the shipped text
        ),
        # column layout: an existing column changed or dropped is refused; an appended column passes
        (
            snapshot(columns={"movements": (("0", "amount", "INTEGER", 1, None, 0),)}),
            snapshot(columns={"movements": (("0", "amount", "TEXT", 1, None, 0),)}),
            True,
        ),
        (
            snapshot(columns={"movements": (("0", "amount", "INTEGER", 1, None, 0),)}),
            snapshot(columns={"movements": ()}),
            True,
        ),
        (
            snapshot(columns={"movements": (("0", "amount", "INTEGER", 1, None, 0),)}),
            snapshot(
                columns={
                    "movements": (
                        ("0", "amount", "INTEGER", 1, None, 0),
                        ("1", "note", "TEXT", 0, None, 0),
                    )
                }
            ),
            False,
        ),
        (
            snapshot(columns={"holds": (("0", "hold_id", "TEXT", 1, None, 1),)}),
            snapshot(columns={}),
            True,
        ),
        (
            snapshot(history=HISTORY),
            snapshot(history=[*HISTORY, (9, "0009_forged", "c")]),
            True,  # history that differs from the migrations applied so far
        ),
    ],
)
def test_each_verification_clause_decides_on_synthetic_snapshots(
    before: migrations_module._Snapshot,
    after: migrations_module._Snapshot,
    expected: bool,
) -> None:
    assert migrations_module._violations(before, after, HISTORY) is expected


def test_a_migration_that_leaves_a_foreign_key_violation_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    before = state(conn)
    sql = (
        "CREATE TABLE parent (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE child (p INTEGER REFERENCES parent(id));\n"
        "INSERT INTO child (p) VALUES (5);\n"
    )
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [*BASE, second(sql)], NOW)
    assert excinfo.value.code == "MIGRATION_FAILED"
    assert state(conn) == before


def test_a_temp_view_cannot_fake_the_migration_history(tmp_path: pathlib.Path) -> None:
    """A caller's temp object named schema_version must not make a pending migration look applied.

    Before the fix the runner read the fake history, skipped migration 2, and reported success.
    Now it reads the real history, sees the connection's temp object, and refuses."""
    conn = migrated(tmp_path)
    extra = second(LEGITIMATE)
    fake = [(m.version, m.name, m.checksum) for m in BASE] + [
        (extra.version, extra.name, extra.checksum)
    ]
    rows = [
        f"SELECT {v} AS version, '{n}' AS migration_name, '{c}' AS checksum, '{NOW}' AS applied_at"
        for v, n, c in fake
    ]
    conn.execute("CREATE TEMP VIEW schema_version AS " + " UNION ALL ".join(rows))
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [*BASE, extra], NOW)
    assert excinfo.value.code == "MIGRATION_FAILED"
    assert conn.execute("SELECT MAX(version) FROM main.schema_version").fetchone() == (
        len(BASE),
    )


# Destructive statements on tables the trigger and verification layers do not guard. The authorizer
# is the only layer for these, so they are tested here with it in place (the Specs ban, specs/05 s.8).
DESTRUCTIVE_ON_OPEN_TABLES = [
    "DROP TABLE holds;",
    "UPDATE movements SET amount_cents = 1;",
    "DELETE FROM retention_metadata;",
    "ALTER TABLE movements DROP COLUMN amount_cents;",
    "ALTER TABLE holds RENAME TO holds_old;",
    "DROP INDEX idx_holds_account_state;",
    "DELETE FROM sqlite_master;",
    "UPDATE sqlite_master SET sql = 'x' WHERE name = 'holds';",
]


@pytest.mark.parametrize("attack", DESTRUCTIVE_ON_OPEN_TABLES)
def test_destructive_changes_to_unguarded_tables_are_refused_with_nothing_changed(
    tmp_path: pathlib.Path, attack: str
) -> None:
    conn = migrated(tmp_path)
    before = state(conn)
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [*BASE, second(attack)], NOW)
    assert excinfo.value.code == "MIGRATION_FAILED"
    assert not conn.in_transaction
    assert state(conn) == before


def test_a_quoted_name_in_a_trigger_is_still_seen_by_the_readiness_check(
    tmp_path: pathlib.Path,
) -> None:
    conn = migrated(tmp_path)
    conn.execute("CREATE TABLE note (x)")
    conn.execute(
        "CREATE TRIGGER quoted AFTER INSERT ON note BEGIN"
        " INSERT INTO 'schema_version' (version, migration_name, checksum, applied_at)"
        f" VALUES (9, '0009_forged', '{HEX}', '2026-10-09T10:00:00Z'); END"
    )
    assert not retained_history_protected(conn)
