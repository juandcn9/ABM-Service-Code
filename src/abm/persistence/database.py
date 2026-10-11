"""SQLite connection settings, transaction unit, and safe error mapping.

specs/03-architecture.md sections 5 and 7, specs/05-data-model.md section 3,
specs/07-operations-and-recovery.md section 3: foreign keys on, WAL, full synchronous
durability, bounded busy timeout, BEGIN IMMEDIATE for every state change.
"""

from __future__ import annotations

import pathlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from abm.domain.results import Failure, failure

MIN_BUSY_TIMEOUT_MS = 1
MAX_BUSY_TIMEOUT_MS = 60_000
DEFAULT_BUSY_TIMEOUT_MS = 5_000

# primary SQLite result codes (the low byte of sqlite_errorcode)
_BUSY, _LOCKED = 5, 6
_UNAVAILABLE = {
    8,
    10,
    11,
    13,
    14,
    26,
}  # readonly, ioerr, corrupt, full, cantopen, notadb


class DatabaseUnavailable(Exception):
    """Opening or configuring the database failed. Carries no path or SQL."""


def open_database(
    path: str | pathlib.Path,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open one connection with the required settings, verified by reading them back.

    The connect timeout installs the busy timeout (PRAGMA values cannot be bound, so none
    is formatted into SQL). The connection is in autocommit mode; transactions are explicit (write_transaction,
    read_transaction). Use one connection per thread of work; sharing one across threads
    needs a lock the caller must provide.
    """
    if (
        type(busy_timeout_ms) is not int
        or not MIN_BUSY_TIMEOUT_MS <= busy_timeout_ms <= MAX_BUSY_TIMEOUT_MS
    ):
        raise DatabaseUnavailable("invalid busy timeout")
    conn = None
    try:
        # sqlite3 turns the timeout into whole milliseconds by truncation; the half millisecond
        # makes every valid value land on the requested one
        conn = sqlite3.connect(
            str(path),
            isolation_level=None,
            timeout=(busy_timeout_ms + 0.5) / 1000,
            check_same_thread=check_same_thread,
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = FULL")
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        settings = (
            conn.execute("PRAGMA foreign_keys").fetchone()[0],
            conn.execute("PRAGMA synchronous").fetchone()[0],  # 2 = FULL
            conn.execute("PRAGMA busy_timeout").fetchone()[0],
        )
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()  # do not leak a half-configured handle
        raise DatabaseUnavailable("database could not be opened") from exc
    # an in-memory database cannot use WAL; every file database must
    wal_ok = mode == "wal" or (str(path) == ":memory:" and mode == "memory")
    if not wal_ok or settings != (1, 2, busy_timeout_ms):
        conn.close()
        raise DatabaseUnavailable("database settings were not applied")
    return conn


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT, or ROLLBACK on any exception, which then propagates.

    Taking the write lock first serializes writers before any idempotency or state read.
    A busy database surfaces as sqlite3.OperationalError, mapped by to_failure.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


@contextmanager
def read_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One read snapshot (WAL). BEGIN is deferred, so the snapshot starts at the first read."""
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        if conn.in_transaction:
            conn.execute("ROLLBACK")  # nothing to commit; ends the snapshot


def to_failure(exc: sqlite3.Error) -> Failure:
    """Map a SQLite error to a stable, safe result. Never includes SQL, paths, or driver text."""
    primary = (getattr(exc, "sqlite_errorcode", None) or 0) & 0xFF
    if primary in (_BUSY, _LOCKED):
        return failure(
            "SERVICE_BUSY",
            "The service is busy. Retry the same request.",
            retryable=True,
        )
    if primary in _UNAVAILABLE:
        return failure("SERVICE_UNREADY", "The service is not ready.")
    return failure("INTERNAL_ERROR", "An unexpected error occurred.")
