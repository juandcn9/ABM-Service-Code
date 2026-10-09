"""Ordered, immutable, forward-only SQLite migrations (DEC-0007; specs/05-data-model.md section 8)."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

# stem = version, underscore, name; the stem is stored as schema_version.migration_name (<= 128 chars)
_STEM = re.compile(r"(\d{4})_[-A-Za-z0-9._~]+")


class MigrationError(Exception):
    """Startup failure carrying only a safe code, never SQL or file contents."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def checksum(sql: str) -> str:
    # LF-normalized so a checkout with CRLF line endings keeps the recorded checksum
    return hashlib.sha256(sql.replace("\r\n", "\n").encode("utf-8")).hexdigest()


_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
# a migration runs inside the runner's transaction, so it may not begin, end, or nest one
_TRANSACTION_CONTROL = re.compile(
    r"\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*(?:begin|commit|end|rollback|savepoint|release)\b",
    re.IGNORECASE | re.DOTALL,
)


def load_migrations(directory: pathlib.Path) -> list[Migration]:
    """Read NNNN_name.sql files; versions must be exactly 1..n with no gap or duplicate.

    Everything wrong with the files is reported here, before any database is touched: an
    entry that is not a plain lowercase .sql file, an unreadable or non-UTF-8 file, a bad
    name, text that is not whole statements, or a statement that controls the transaction.
    """
    found: list[Migration] = []
    try:
        entries = sorted(directory.iterdir())
        for path in entries:
            match = _STEM.fullmatch(path.stem)
            if (
                path.suffix != ".sql"
                or not path.is_file()
                or not match
                or len(path.stem) > 128
            ):
                raise MigrationError("MIGRATION_FILES_INVALID")
            sql = path.read_text(encoding="utf-8")
            for statement in _statements(sql):
                if _TRANSACTION_CONTROL.match(statement):
                    raise MigrationError("MIGRATION_FILES_INVALID")
            found.append(Migration(int(match.group(1)), path.stem, sql, checksum(sql)))
    except (OSError, UnicodeError, ValueError) as exc:
        raise MigrationError("MIGRATION_FILES_INVALID") from exc
    if [m.version for m in found] != list(range(1, len(found) + 1)):
        raise MigrationError("MIGRATION_FILES_INVALID")
    return found


def _statements(sql: str) -> Iterator[str]:
    # executescript() would commit first, so split and run each statement in our transaction
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ""
    if _COMMENTS.sub(
        "", buffer
    ).strip():  # a trailing comment is fine; half a statement is not
        raise MigrationError("MIGRATION_FILES_INVALID")


# Defense in depth behind the lexical check in load_migrations. While a migration's statements
# run, SQLite itself enforces an allowlist, because a migration is reviewed text but must not be
# trusted to keep the guarantees the Specs make about retained history:
#  - no transaction control, savepoints, ATTACH, or DETACH (they could end the runner's transaction);
#  - no PRAGMA except foreign_keys (settings such as ignore_check_constraints or query_only would
#    outlive the migration on the shared connection);
#  - no UPDATE, DELETE, DROP, or ALTER of a retained table, no dropping its immutability triggers,
#    and no shadowing it with a temp table: retained history is never rewritten (BT-05, DEC-0002)
#    and a destructive migration is a governance escalation (specs/07 section 6).
# Leading-token tricks (`;ROLLBACK;`, a byte-order mark, comments) cannot get around this because
# the authorizer acts on the parsed statement.
PROTECTED_TABLES = frozenset(
    {
        "schema_version",
        "ledger_entries",
        "audit_trace",
        "movement_evidence",
        "idempotency_outcomes",
    }
)
# the immutability triggers of contracts/sqlite-schema.sql; tests pin this set to migration 0001
PROTECTED_TRIGGERS = frozenset(
    {
        "schema_version_no_update",
        "schema_version_no_delete",
        "movement_evidence_no_update",
        "movement_evidence_no_delete",
        "ledger_entries_no_update",
        "ledger_entries_no_delete",
        "audit_trace_no_update",
        "audit_trace_no_delete",
    }
)
_ALLOWED_PRAGMAS = frozenset(
    {"foreign_keys"}
)  # migration 0001 opens with PRAGMA foreign_keys = ON
_DENIED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
    }
)
# actions whose first argument is the table they act on
_TABLE_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
    }
)


def _migration_authorizer(
    action: int,
    arg1: str | None,
    arg2: str | None,
    _db: str | None,
    _source: str | None,
) -> int:
    first = (arg1 or "").lower()
    second = (arg2 or "").lower()
    if action in _DENIED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA:
        return sqlite3.SQLITE_OK if first in _ALLOWED_PRAGMAS else sqlite3.SQLITE_DENY
    if action in _TABLE_ACTIONS and first in PROTECTED_TABLES:
        return sqlite3.SQLITE_DENY
    if (
        action in (sqlite3.SQLITE_DROP_TRIGGER, sqlite3.SQLITE_ALTER_TABLE)
        and second in PROTECTED_TABLES
    ):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


# Connection settings that must not change across a migration (all are read-only to a migration
# already; this is the second, independent check).
_STATE_PRAGMAS = (
    "PRAGMA foreign_keys",
    "PRAGMA defer_foreign_keys",
    "PRAGMA ignore_check_constraints",
    "PRAGMA recursive_triggers",
    "PRAGMA trusted_schema",
    "PRAGMA query_only",
    "PRAGMA locking_mode",
    "PRAGMA synchronous",
    "PRAGMA busy_timeout",
)


def _connection_state(conn: sqlite3.Connection) -> tuple[object, ...]:
    return tuple(conn.execute(sql).fetchone()[0] for sql in _STATE_PRAGMAS)


def _trigger_sql(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row[0]: row[1] or ""
        for row in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
        )
    }


def _mentions_retained_table(sql: str) -> bool:
    lowered = sql.lower()
    return any(table in lowered for table in PROTECTED_TABLES)


def retained_history_protected(conn: sqlite3.Connection) -> bool:
    """True if every immutability trigger exists and no other trigger touches a retained table.

    Used after a migration and by readiness (tampering that bypasses the runner).
    """
    triggers = _trigger_sql(conn)
    return PROTECTED_TRIGGERS <= triggers.keys() and not any(
        name not in PROTECTED_TRIGGERS and _mentions_retained_table(sql)
        for name, sql in triggers.items()
    )


def _migration_left_everything_intact(
    conn: sqlite3.Connection,
    history_before: list[tuple[int, str, str]],
    triggers_before: dict[str, str],
    state_before: tuple[object, ...],
) -> bool:
    """Checked inside the transaction just before COMMIT; a False result rolls everything back."""
    triggers_after = _trigger_sql(conn)
    kept = all(triggers_after.get(name) == sql for name, sql in triggers_before.items())
    added_safely = all(
        name in PROTECTED_TRIGGERS
        or name in triggers_before
        or not _mentions_retained_table(sql)
        for name, sql in triggers_after.items()
    )
    return (
        kept
        and added_safely
        and _applied(conn)[: len(history_before)] == history_before
        and _connection_state(conn) == state_before
        and conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        and not conn.execute("PRAGMA foreign_key_check").fetchall()
    )


def _applied(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if not tables:
        return []
    if "schema_version" not in tables:
        # a populated database with no migration history is not ours to modify
        raise MigrationError("UNSUPPORTED_SCHEMA_VERSION")
    return [
        (row[0], row[1], row[2])
        for row in conn.execute(
            "SELECT version, migration_name, checksum FROM schema_version ORDER BY version"
        )
    ]


def apply_migrations(
    conn: sqlite3.Connection, migrations: Sequence[Migration], applied_at: str
) -> None:
    """Apply every pending migration in one transaction, or change nothing.

    conn must be in autocommit mode (isolation_level None). applied_at is a UTC
    ISO-8601 'Z' instant from the injected clock.
    """
    if conn.isolation_level is not None or conn.in_transaction:
        raise MigrationError("MIGRATION_FAILED")
    try:
        conn.execute("BEGIN IMMEDIATE")  # serializes concurrent migrators
        applied = _applied(conn)
        if len(applied) > len(migrations):
            raise MigrationError("UNSUPPORTED_SCHEMA_VERSION")
        for done, known in zip(applied, migrations, strict=False):
            if done != (known.version, known.name, known.checksum):
                raise MigrationError("MIGRATION_CHECKSUM_MISMATCH")
        triggers_before = _trigger_sql(conn)
        state_before = _connection_state(conn)
        for migration in migrations[len(applied) :]:
            conn.set_authorizer(_migration_authorizer)
            try:
                for statement in _statements(migration.sql):
                    conn.execute(statement)
            finally:
                conn.set_authorizer(None)
            conn.execute(
                "INSERT INTO schema_version (version, migration_name, checksum, applied_at)"
                " VALUES (?, ?, ?, ?)",
                (migration.version, migration.name, migration.checksum, applied_at),
            )
        if len(applied) < len(migrations) and not _migration_left_everything_intact(
            conn, applied, triggers_before, state_before
        ):
            raise MigrationError("MIGRATION_FAILED")
        conn.execute("COMMIT")
    except (
        BaseException
    ) as exc:  # never leave the migration transaction open, whatever failed
        _rollback(conn)
        if isinstance(exc, sqlite3.Error):
            raise MigrationError("MIGRATION_FAILED") from exc
        raise


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.execute("ROLLBACK")
