"""Connection settings, transaction unit, and error mapping (INV-06, NFR-04, TEST-16 and TEST-38 foundations)."""

from __future__ import annotations

import itertools
import pathlib
import sqlite3
import threading
import time
from typing import Any, cast

import pytest

from abm.domain.results import Failure
from abm.persistence.database import (
    DatabaseUnavailable,
    open_database,
    read_transaction,
    to_failure,
    write_transaction,
)


@pytest.fixture
def db_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "abm.sqlite3"
    conn = open_database(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE child (id INTEGER PRIMARY KEY, t_id INTEGER NOT NULL REFERENCES t(id))"
    )
    conn.close()
    return path


def pragma(conn: sqlite3.Connection, name: str) -> object:
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def count(conn: sqlite3.Connection, table: str = "t") -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_required_settings_are_applied_and_verified(db_path: pathlib.Path) -> None:
    conn = open_database(db_path, busy_timeout_ms=1234)
    assert pragma(conn, "foreign_keys") == 1
    assert pragma(conn, "journal_mode") == "wal"
    assert pragma(conn, "synchronous") == 2  # FULL
    assert pragma(conn, "busy_timeout") == 1234
    assert conn.isolation_level is None  # explicit transactions only


def test_foreign_keys_are_enforced(db_path: pathlib.Path) -> None:
    conn = open_database(db_path)
    with pytest.raises(sqlite3.IntegrityError), write_transaction(conn):
        conn.execute("INSERT INTO child (t_id) VALUES (999)")
    assert count(conn, "child") == 0


def test_memory_database_is_allowed_for_tests() -> None:
    conn = open_database(":memory:")
    assert pragma(conn, "foreign_keys") == 1


@pytest.mark.parametrize("bad", [0, -1, 60_001, 1.5, "5000", None, True])
def test_busy_timeout_must_be_a_bounded_integer(
    db_path: pathlib.Path, bad: object
) -> None:
    with pytest.raises(DatabaseUnavailable):
        open_database(db_path, busy_timeout_ms=bad)  # type: ignore[arg-type]


def test_unopenable_path_fails_without_leaking_it(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "no-such-dir" / "secret-name.sqlite3"
    with pytest.raises(DatabaseUnavailable) as excinfo:
        open_database(missing)
    assert "secret-name" not in str(excinfo.value)


def test_commit_makes_every_step_visible_together(db_path: pathlib.Path) -> None:
    conn = open_database(db_path)
    with write_transaction(conn):
        conn.execute("INSERT INTO t (v) VALUES ('a')")
        conn.execute("INSERT INTO t (v) VALUES ('b')")
    assert count(open_database(db_path)) == 2


def test_failure_after_every_step_leaves_all_effects_or_none(
    db_path: pathlib.Path,
) -> None:
    steps = [
        "INSERT INTO t (v) VALUES ('1')",
        "INSERT INTO t (v) VALUES ('2')",
        "INSERT INTO t (v) VALUES ('3')",
    ]
    for fail_after in range(len(steps) + 1):
        conn = open_database(db_path)
        with pytest.raises(RuntimeError), write_transaction(conn):
            for done, statement in enumerate(steps):
                if done == fail_after:
                    raise RuntimeError("injected")
                conn.execute(statement)
            raise RuntimeError("injected after last step")
        assert not conn.in_transaction
        assert count(open_database(db_path)) == 0, fail_after


def test_constraint_failure_inside_a_step_rolls_everything_back(
    db_path: pathlib.Path,
) -> None:
    conn = open_database(db_path)
    with pytest.raises(sqlite3.IntegrityError), write_transaction(conn):
        conn.execute("INSERT INTO t (v) VALUES ('kept?')")
        conn.execute("INSERT INTO t (v) VALUES (NULL)")
    assert count(conn) == 0


def test_baseexception_also_rolls_back(db_path: pathlib.Path) -> None:
    conn = open_database(db_path)
    with pytest.raises(KeyboardInterrupt), write_transaction(conn):
        conn.execute("INSERT INTO t (v) VALUES ('x')")
        raise KeyboardInterrupt
    assert count(conn) == 0 and not conn.in_transaction


def test_second_writer_is_refused_with_a_safe_retryable_busy_failure(
    db_path: pathlib.Path,
) -> None:
    holder = open_database(db_path)
    other = open_database(db_path, busy_timeout_ms=50)
    with write_transaction(holder):
        holder.execute("INSERT INTO t (v) VALUES ('held')")
        with (
            pytest.raises(sqlite3.OperationalError) as excinfo,
            write_transaction(other),
        ):
            pytest.fail("a second writer must not enter")
        result = to_failure(excinfo.value)
    assert isinstance(result, Failure)
    assert result.error.code == "SERVICE_BUSY" and result.error.retryable is True
    assert not other.in_transaction
    assert count(open_database(db_path)) == 1  # only the holder's committed row


def test_writers_are_serialized_not_interleaved(db_path: pathlib.Path) -> None:
    def work(n: int) -> None:
        conn = open_database(db_path, busy_timeout_ms=10_000)
        with write_transaction(conn):
            for i in range(20):
                conn.execute("INSERT INTO t (v) VALUES (?)", (f"{n}-{i}",))
        conn.close()

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    conn = open_database(db_path)
    assert count(conn) == 80
    owners = [
        row[0].split("-")[0] for row in conn.execute("SELECT v FROM t ORDER BY id")
    ]
    changes = sum(1 for a, b in itertools.pairwise(owners) if a != b)
    assert changes == 3  # each transaction's 20 rows are contiguous


def test_second_writer_waits_for_the_first_and_then_sees_its_commit(
    db_path: pathlib.Path,
) -> None:
    # Without BEGIN IMMEDIATE the second writer reads a stale snapshot and fails on its write,
    # and it does not wait for the lock, so both the outcome and the wait are asserted.
    first = open_database(db_path, busy_timeout_ms=10_000)
    seen: list[int] = []
    waited: list[float] = []
    errors: list[BaseException] = []

    def contend() -> None:
        second = open_database(
            db_path, busy_timeout_ms=10_000
        )  # opened on the thread that uses it
        started = time.monotonic()
        try:
            with write_transaction(second):
                waited.append(time.monotonic() - started)
                seen.append(count(second))
                second.execute("INSERT INTO t (v) VALUES ('second')")
        except sqlite3.Error as exc:  # reported on the test thread below
            errors.append(exc)
        finally:
            second.close()

    with write_transaction(first):
        first.execute("INSERT INTO t (v) VALUES ('first')")
        thread = threading.Thread(target=contend)
        thread.start()
        time.sleep(0.2)  # the second writer is now waiting for the lock
    thread.join()
    first.close()
    assert errors == []
    assert waited and waited[0] >= 0.1  # it really waited for the first writer's lock
    assert seen == [1]  # then read the first writer's row
    assert count(open_database(db_path)) == 2


def test_every_valid_busy_timeout_is_applied_exactly() -> None:
    # every value in the accepted range; the driver truncates, so plain division fails 372 of them
    for busy_timeout_ms in range(1, 60_001):
        conn = open_database(":memory:", busy_timeout_ms=busy_timeout_ms)
        assert conn.execute("PRAGMA busy_timeout").fetchone() == (busy_timeout_ms,)
        conn.close()


def test_read_transaction_sees_one_consistent_snapshot(db_path: pathlib.Path) -> None:
    reader = open_database(db_path)
    writer = open_database(db_path)
    with write_transaction(writer):
        writer.execute("INSERT INTO t (v) VALUES ('before')")
    with read_transaction(reader):
        assert count(reader) == 1
        with write_transaction(writer):  # a commit mid-snapshot must stay invisible
            writer.execute("INSERT INTO t (v) VALUES ('during')")
        assert count(reader) == 1
    assert count(reader) == 2
    assert not reader.in_transaction


def test_disk_full_is_a_safe_failure_with_no_partial_effect(
    db_path: pathlib.Path,
) -> None:
    conn = open_database(db_path)
    conn.execute(f"PRAGMA max_page_count = {int(str(pragma(conn, 'page_count')))}")
    with pytest.raises(sqlite3.OperationalError) as excinfo, write_transaction(conn):
        for i in range(500):
            conn.execute("INSERT INTO t (v) VALUES (?)", ("x" * 4000 + str(i),))
    result = to_failure(excinfo.value)
    assert isinstance(result, Failure)
    assert result.error.code == "SERVICE_UNREADY" and result.error.retryable is False
    assert count(conn) == 0


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (5, "SERVICE_BUSY"),  # SQLITE_BUSY
        (6, "SERVICE_BUSY"),  # SQLITE_LOCKED
        (517, "SERVICE_BUSY"),  # SQLITE_BUSY_SNAPSHOT: the primary code is what counts
        (8, "SERVICE_UNREADY"),  # SQLITE_READONLY
        (10, "SERVICE_UNREADY"),  # SQLITE_IOERR
        (11, "SERVICE_UNREADY"),  # SQLITE_CORRUPT
        (13, "SERVICE_UNREADY"),  # SQLITE_FULL
        (14, "SERVICE_UNREADY"),  # SQLITE_CANTOPEN
        (26, "SERVICE_UNREADY"),  # SQLITE_NOTADB
        (1, "INTERNAL_ERROR"),  # SQLITE_ERROR is not a readiness problem
    ],
)
def test_each_sqlite_code_maps_to_its_safe_failure(code: int, expected: str) -> None:
    class Coded(sqlite3.DatabaseError):
        sqlite_errorcode = code

    result = to_failure(Coded("driver text"))
    assert isinstance(result, Failure)
    assert result.error.code == expected


def test_error_mapping_never_exposes_driver_text() -> None:
    secret = "SELECT secret FROM /private/path.sqlite3"
    for exc in (
        sqlite3.OperationalError(secret),
        sqlite3.IntegrityError(secret),
        sqlite3.DatabaseError(secret),
    ):
        result = to_failure(exc)
        assert isinstance(result, Failure)
        assert result.error.code == "INTERNAL_ERROR"
        assert (
            "secret" not in result.error.safe_message
            and "private" not in result.error.safe_message
        )


class _RecordingConnection(sqlite3.Connection):
    """Records each statement before running it, so a test can see what open_database issued."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.statements: list[str] = []

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        self.statements.append(sql)
        return super().execute(sql, parameters)


def test_a_file_database_is_opened_with_synchronous_full(
    db_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The SQLite default on this build is already FULL, so the value alone cannot show that the PRAGMA
    # ran. The statement issued by open_database is what is checked.
    real_connect = sqlite3.connect

    def recording_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        return real_connect(*args, **kwargs, factory=_RecordingConnection)

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    conn = open_database(db_path)
    try:
        assert pragma(conn, "synchronous") == 2  # FULL
        recorded = cast(_RecordingConnection, conn).statements
        assert "PRAGMA synchronous = FULL" in recorded
    finally:
        conn.close()
