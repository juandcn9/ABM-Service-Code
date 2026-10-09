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


# Defense in depth behind the lexical check in load_migrations: while a migration's statements
# run, SQLite itself refuses anything that could end the runner's transaction, nest one, attach
# another database, or rewrite the schema table directly. Leading-token tricks (`;ROLLBACK;`,
# a byte-order mark, comments) cannot get around this because it acts on the parsed statement.
_DENIED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
    }
)


def _migration_authorizer(
    action: int,
    arg1: str | None,
    _arg2: str | None,
    _db: str | None,
    _source: str | None,
) -> int:
    if action in _DENIED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() == "writable_schema":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


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
