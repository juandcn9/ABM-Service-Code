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


def load_migrations(directory: pathlib.Path) -> list[Migration]:
    """Read NNNN_name.sql files; versions must be exactly 1..n with no gap or duplicate."""
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _STEM.fullmatch(path.stem)
        if not match or len(path.stem) > 128:
            raise MigrationError("MIGRATION_FILES_INVALID")
        sql = path.read_text(encoding="utf-8")
        found.append(Migration(int(match.group(1)), path.stem, sql, checksum(sql)))
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
    if buffer.strip():
        raise MigrationError("MIGRATION_FILES_INVALID")


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
            for statement in _statements(migration.sql):
                conn.execute(
                    statement
                )  # sql-scan: migration files are reviewed and checksummed
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
