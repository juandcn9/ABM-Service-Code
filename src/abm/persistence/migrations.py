"""Ordered, immutable, forward-only SQLite migrations (DEC-0007; specs/05-data-model.md section 8).

A migration file is reviewed text, but the runner does not trust it with retained history or the
shared connection (BT-05, DEC-0002; specs/07 section 6 makes a destructive migration a governance
escalation). Three layers, none of which depends on recognizing a particular attack:

1. Prevent: while a migration's statements run, a SQLite authorizer allows only what an additive
   migration needs (see _migration_authorizer).
2. Verify: before COMMIT, the runner compares the actual retained data, the retained schema, the
   temp schema, the history table, and the connection settings with what they were before the
   migration, and rolls everything back on any difference (see _violations).
3. Detect: retained_history_protected() lets readiness notice tampering that bypassed the runner.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
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


# quoted text is kept (SQLite accepts 'table' as a name) and only comments are blanked
_QUOTED_OR_COMMENT = re.compile(
    r"""('(?:[^']|'')*'|"(?:[^"]|"")*")|--[^\n]*|/\*.*?\*/""", re.DOTALL
)
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
    start = 0
    for end, char in enumerate(sql):  # a line can hold several statements
        if char == ";" and sqlite3.complete_statement(sql[start : end + 1]):
            yield sql[start : end + 1]
            start = end + 1
    # a trailing comment is fine; half a statement is not
    if _COMMENTS.sub("", sql[start:]).strip():
        raise MigrationError("MIGRATION_FILES_INVALID")


# --- what is retained, pinned to the shipped schema ---------------------------------------------

# SHA-256 of each definition exactly as SQLite stores it (sqlite_master.sql) after migration 0001,
# which is contracts/sqlite-schema.sql of Specs v1.0.1. A test pins these to the real file.
_PINNED_TABLES = {
    "audit_trace": "8a7842715f6e3b3f0f611f1ce97bcc89ffcb19ad86acef90eac7c9d76b4c38e8",
    "idempotency_outcomes": "00ff031092126666843cf810162654d55473d725c76b8af1df07c4b369c2958b",
    "ledger_entries": "9b3cf293ad3bb4edddaee119fda1f3230ea5e7de6d3d0caa3d567fb4f2aac857",
    "movement_evidence": "6bae782ace1a47c25d9552f4436ee320e095eaee6c47eb7ba0af7b686727b759",
    "schema_version": "8e60a84e34f7a6674e33a4b3a6e29db56bd300c1746a87629101bc89bd140175",
}
_PINNED_TRIGGERS = {
    "audit_trace_no_delete": "3ca790b6fa9cf21ade53d139119e54026ac6da956dbb540f90aa35d5da4004ff",
    "audit_trace_no_update": "ad38a130e875aa11f67858c32b35964aa4dbdae129afa922bc7a697253235d4f",
    "ledger_entries_no_delete": "f5f8f2cf17b3915c9a5c0e912a242af402a90dba01bf7b3f16d354d3d069cf8c",
    "ledger_entries_no_update": "062bda50319ad28fc35cbe32901a574e08b65e6add50c30adbd41a0723bfb824",
    "movement_evidence_no_delete": "486b1c68085778aa66cade6fa1f2289a79ff9217a4f6e0a84b63bd8d55df8f8b",
    "movement_evidence_no_update": "13cd858bba003563cdc1e88fb73ad61f1f7c52d68d1b3b321fac891ed35aa3c0",
    "schema_version_no_delete": "bbeab78a896468f0f9d528a7a625987117a84630b63528140424ad5735ac2e8f",
    "schema_version_no_update": "462c1a6ac76416e0e81d74daea7d360713b5af60ac128fa9b4aa816fb340f292",
}
PROTECTED_TABLES = frozenset(_PINNED_TABLES)
PROTECTED_TRIGGERS = frozenset(_PINNED_TRIGGERS)

# Retained rows are compared in full, in rowid order. One fixed statement per table (no SQL is
# ever built from a name). schema_version is not listed: the runner itself appends to it, and its
# contents are checked against the expected history instead.
# main. is explicit so a temp object with the same name cannot be what gets compared
_ROW_QUERIES = {
    "audit_trace": "SELECT * FROM main.audit_trace ORDER BY rowid",
    "idempotency_outcomes": "SELECT * FROM main.idempotency_outcomes ORDER BY rowid",
    "ledger_entries": "SELECT * FROM main.ledger_entries ORDER BY rowid",
    "movement_evidence": "SELECT * FROM main.movement_evidence ORDER BY rowid",
}
_RETAINED_SCHEMA = (
    "SELECT type, name, tbl_name, COALESCE(sql, '') FROM sqlite_master WHERE type = 'trigger'"
    " OR tbl_name IN ('audit_trace', 'idempotency_outcomes', 'ledger_entries',"
    " 'movement_evidence', 'schema_version')"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mentions_retained_table(sql: str) -> bool:
    """A whole-word reference outside comments; quoted forms such as 'ledger_entries' count."""
    code = _QUOTED_OR_COMMENT.sub(lambda m: m.group(1) or " ", sql).lower()
    return any(
        re.search(rf"(?<![\w$]){table}(?![\w$])", code) for table in PROTECTED_TABLES
    )


# --- prevent: the authorizer ---------------------------------------------------------------------

# Anything that could end the runner's transaction, nest one, reach another database, create
# per-connection objects that shadow or intercept retained tables, or load code.
_DENIED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_VTABLE,
        # destructive work on any table: the Specs permit no destructive migration (specs/05 s.8).
        # shortcut: ALTER TABLE is refused for all tables because SQLite reports ADD COLUMN and
        # DROP COLUMN alike, upgrade to allow ADD COLUMN once told apart
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
    }
)
# inserts into a retained table would append forged history; SQLite's own bookkeeping is refused too
_TABLE_ACTIONS = frozenset({sqlite3.SQLITE_INSERT})
_ALLOWED_PRAGMAS = frozenset(
    {"foreign_keys", "quick_check"}
)  # 0001 opens with PRAGMA foreign_keys = ON; ALTER TABLE runs the read-only quick_check


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
    if action == sqlite3.SQLITE_FUNCTION and second == "load_extension":
        return sqlite3.SQLITE_DENY
    if action in _TABLE_ACTIONS and (
        first in PROTECTED_TABLES or first == "sqlite_sequence"
    ):
        return sqlite3.SQLITE_DENY
    # CREATE makes SQLite itself update and delete rows of sqlite_master; a migration cannot
    # reach that table directly (writable_schema is refused above)
    if (
        action in (sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)
        and first != "sqlite_master"
    ):
        return sqlite3.SQLITE_DENY
    # additive ALTER on other tables is allowed; verification checks the column layout afterwards
    if action == sqlite3.SQLITE_ALTER_TABLE and second in PROTECTED_TABLES:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


# --- verify: compare before and after ------------------------------------------------------------

# Connection settings that must not change across a migration. A migration cannot set any of them
# (the authorizer refuses every PRAGMA but foreign_keys); this is the second, independent check.
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
    "PRAGMA legacy_alter_table",
    "PRAGMA cell_size_check",
    "PRAGMA reverse_unordered_selects",
    "PRAGMA automatic_index",
    "PRAGMA read_uncommitted",
    "PRAGMA secure_delete",
    "PRAGMA max_page_count",
    "PRAGMA journal_mode",
    "PRAGMA user_version",
    "PRAGMA application_id",
    "PRAGMA writable_schema",  # lets a migration rewrite sqlite_master directly
)


@dataclass(frozen=True)
class _Snapshot:
    rows: dict[
        str, tuple[int, str]
    ]  # retained table -> (row count, digest of every row)
    sequences: dict[str, int]  # retained AUTOINCREMENT counters
    schema: frozenset[
        tuple[str, str, str, str]
    ]  # retained tables' objects and every trigger
    temp: frozenset[tuple[str, str, str]]  # per-connection (temp) schema objects
    columns: dict[
        str, tuple[tuple[object, ...], ...]
    ]  # every user table's column layout
    state: tuple[object, ...]  # connection settings
    history: list[tuple[int, str, str]]  # applied migrations


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _snapshot(conn: sqlite3.Connection) -> _Snapshot:
    present = _tables(conn)
    rows: dict[str, tuple[int, str]] = {}
    for table, query in _ROW_QUERIES.items():
        if table in present:
            digest = hashlib.sha256()
            count = 0
            for row in conn.execute(query):
                digest.update(repr(row).encode("utf-8"))
                count += 1
            rows[table] = (count, digest.hexdigest())
    sequences: dict[str, int] = {}
    if "sqlite_sequence" in present:
        sequences = {
            name: seq
            for name, seq in conn.execute("SELECT name, seq FROM sqlite_sequence")
            if name in PROTECTED_TABLES
        }
    return _Snapshot(
        rows=rows,
        sequences=sequences,
        schema=frozenset(
            (r[0], r[1], r[2], r[3]) for r in conn.execute(_RETAINED_SCHEMA)
        ),
        temp=frozenset(
            (r[0], r[1], r[2])
            for r in conn.execute(
                "SELECT type, name, COALESCE(sql, '') FROM sqlite_temp_master"
            )
        ),
        # database_list catches an ATTACHed database that would outlive the migration
        state=(
            *(conn.execute(sql).fetchone()[0] for sql in _STATE_PRAGMAS),
            tuple(conn.execute("PRAGMA database_list")),
        ),
        columns={
            name: tuple(
                conn.execute(
                    'SELECT cid, name, type, "notnull", dflt_value, pk FROM pragma_table_info(?)',
                    (name,),
                ).fetchall()
            )
            for name in present
            if not name.startswith("sqlite_")
        },
        history=_applied(conn),
    )


def _violations(
    before: _Snapshot, after: _Snapshot, expected_history: list[tuple[int, str, str]]
) -> bool:
    """True if the migration changed anything it must not have."""
    # 1. every retained row that existed is untouched; tables created now start empty
    for table, (count, digest) in after.rows.items():
        if table in before.rows:
            if before.rows[table] != (count, digest):
                return True
        elif count != 0:
            return True  # a fresh retained table cannot arrive with rows
    if any(table not in after.rows for table in before.rows):
        return True
    # 2. retained AUTOINCREMENT counters are untouched, and new ones start at zero
    for table, seq in after.sequences.items():
        if seq != before.sequences.get(table, 0):
            return True
    if any(table not in after.sequences for table in before.sequences):
        return True
    # 3. nothing that existed was changed or removed
    if not before.schema <= after.schema:
        return True
    # 4. everything new is acceptable: pinned objects must match, other triggers must not touch
    #    a retained table
    for kind, name, _table, sql in after.schema - before.schema:
        if (
            kind == "table"
            and name in _PINNED_TABLES
            and _sha(sql) != _PINNED_TABLES[name]
        ):
            return True
        if kind == "trigger":
            if name in _PINNED_TRIGGERS:
                if _sha(sql) != _PINNED_TRIGGERS[name]:
                    return True
            elif _mentions_retained_table(sql):
                return True
    # 5. no per-connection objects, and settings unchanged
    if after.temp != before.temp or after.temp:
        return True
    if after.state != before.state:
        return True
    # 6. the history table holds exactly the migrations applied so far
    if after.history != expected_history:
        return True
    # 7. no table disappears and no existing column is dropped, renamed, or changed; appends pass
    for table, layout in before.columns.items():
        now = after.columns.get(table)
        if now is None or now[: len(layout)] != layout:
            return True
    return False


def _integrity_ok(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        and not conn.execute("PRAGMA foreign_key_check").fetchall()
    )


# --- detect: used by readiness -------------------------------------------------------------------


def retained_history_protected(conn: sqlite3.Connection) -> bool:
    """True if every retained table and immutability trigger exists exactly as shipped.

    Also requires that no other trigger touches a retained table and that this connection has no
    temp objects. Meant for the readiness check (tampering that bypassed the migration runner).
    """
    schema = {
        (row[0], row[1]): row[3]
        for row in conn.execute(_RETAINED_SCHEMA)
        if row[0] in ("table", "trigger")
    }
    if any(
        _sha(schema.get(("table", name), "")) != digest
        for name, digest in _PINNED_TABLES.items()
    ):
        return False
    if any(
        _sha(schema.get(("trigger", name), "")) != digest
        for name, digest in _PINNED_TRIGGERS.items()
    ):
        return False
    if any(
        name not in _PINNED_TRIGGERS and _mentions_retained_table(sql)
        for (kind, name), sql in schema.items()
        if kind == "trigger"
    ):
        return False
    return not conn.execute("SELECT 1 FROM sqlite_temp_master LIMIT 1").fetchall()


# --- the runner ----------------------------------------------------------------------------------


def _applied(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM main.sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
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
            "SELECT version, migration_name, checksum FROM main.schema_version ORDER BY version"
        )
    ]


def _deadline_handler(seconds: float) -> Callable[[], int]:
    deadline = time.monotonic() + seconds

    def interrupt() -> int:
        return (
            1 if time.monotonic() > deadline else 0
        )  # nonzero aborts the running statement

    return interrupt


def apply_migrations(
    conn: sqlite3.Connection,
    migrations: Sequence[Migration],
    applied_at: str,
    time_limit_seconds: float = 600.0,
) -> None:
    """Apply every pending migration in one transaction, or change nothing.

    conn must be in autocommit mode (isolation_level None) and is owned by the caller for the
    duration of the call: any authorizer or progress handler installed on it is removed. applied_at
    is a UTC ISO-8601 'Z' instant from the injected clock. A statement running longer than
    time_limit_seconds is interrupted (the whole run then rolls back).
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
        pending = migrations[len(applied) :]
        for index, migration in enumerate(pending, start=len(applied) + 1):
            before = _snapshot(conn)
            conn.set_authorizer(_migration_authorizer)
            conn.set_progress_handler(_deadline_handler(time_limit_seconds), 10_000)
            try:
                for statement in _statements(migration.sql):
                    conn.execute(statement)
            finally:
                conn.set_authorizer(None)
                conn.set_progress_handler(None, 0)
            conn.execute(
                "INSERT INTO main.schema_version (version, migration_name, checksum, applied_at)"
                " VALUES (?, ?, ?, ?)",
                (migration.version, migration.name, migration.checksum, applied_at),
            )
            expected = [(m.version, m.name, m.checksum) for m in migrations[:index]]
            if _violations(before, _snapshot(conn), expected):
                raise MigrationError("MIGRATION_FAILED")
        if pending and not _integrity_ok(conn):
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
