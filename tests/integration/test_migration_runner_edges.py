"""Runner edge cases from the independent review: file validation, locks, concurrency, ledger triggers."""

from __future__ import annotations

import pathlib
import sqlite3
import threading

import pytest

from abm.persistence.migrations import (
    Migration,
    MigrationError,
    apply_migrations,
    checksum,
    load_migrations,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
NOW = "2026-10-09T12:00:00Z"


def file_db(tmp_path: pathlib.Path, timeout: float = 5.0) -> sqlite3.Connection:
    return sqlite3.connect(
        tmp_path / "m.sqlite3", isolation_level=None, timeout=timeout
    )


def folder(tmp_path: pathlib.Path, files: dict[str, bytes]) -> pathlib.Path:
    directory = tmp_path / f"m{len(list(tmp_path.iterdir()))}"
    directory.mkdir()
    for name, content in files.items():
        (directory / name).write_bytes(content)
    return directory


def code(excinfo: pytest.ExceptionInfo[MigrationError]) -> str:
    return excinfo.value.code


@pytest.mark.parametrize(
    "sql",
    [
        b"CREATE TABLE a(x); ROLLBACK; CREATE TABLE b(y);",
        b"CREATE TABLE a(x);\nROLLBACK;\nCREATE TABLE b(y);\n",
        b"CREATE TABLE a(x);\nCOMMIT;\n",
        b"BEGIN;\nCREATE TABLE a(x);\n",
        b"-- note\nbegin immediate;\n",
        b"/* note */ END;\n",
        b"SAVEPOINT s;\n",
        b"RELEASE s;\n",
    ],
)
def test_transaction_control_in_a_migration_is_rejected_before_any_run(
    tmp_path: pathlib.Path, sql: bytes
) -> None:
    directory = folder(tmp_path, {"0001_x.sql": sql})
    # statements are split by line; a same-line ROLLBACK is caught at apply time instead
    try:
        load_migrations(directory)
    except MigrationError as err:
        assert err.code == "MIGRATION_FILES_INVALID"
        return
    conn = file_db(tmp_path)
    migration = Migration(1, "0001_x", sql.decode(), checksum(sql.decode()))
    with pytest.raises(MigrationError):
        apply_migrations(conn, [migration], NOW)
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def test_a_trigger_body_is_not_mistaken_for_transaction_control(
    tmp_path: pathlib.Path,
) -> None:
    sql = (
        b"CREATE TABLE a(x);\n"
        b"CREATE TRIGGER t BEFORE UPDATE ON a\nBEGIN SELECT RAISE(ABORT, 'no'); END;\n"
    )
    assert len(load_migrations(folder(tmp_path, {"0001_x.sql": sql}))) == 1


@pytest.mark.parametrize(
    "files",
    [
        {"0001_a.sql": b"\xff\xfe"},  # not UTF-8
        {
            "0001_a.sql": b"CREATE TABLE a(x);\nCREATE TABLE b(y"
        },  # half a statement at the end
        {
            "0001_a.sql": b"SELECT 1;",
            "0002_b.SQL": b"SELECT 2;",
        },  # wrong-case suffix hides a gap
        {"0001_a.sql": b"SELECT 1;", "notes.txt": b"x"},  # stray file
        {"0001_a.sql": b"SELECT 1;", "0002_b.sql.bak": b"x"},
        {"0001_a.sql": b"SELECT 1;", ".gitkeep": b""},
    ],
)
def test_loader_reports_every_file_problem_as_one_safe_code(
    tmp_path: pathlib.Path, files: dict[str, bytes]
) -> None:
    with pytest.raises(MigrationError) as excinfo:
        load_migrations(folder(tmp_path, files))
    assert code(excinfo) == "MIGRATION_FILES_INVALID"
    assert str(excinfo.value) == "MIGRATION_FILES_INVALID"  # no path or file text


def test_a_directory_named_like_a_migration_is_rejected_without_leaking_its_path(
    tmp_path: pathlib.Path,
) -> None:
    directory = folder(tmp_path, {})
    (directory / "0001_a.sql").mkdir()
    with pytest.raises(MigrationError) as excinfo:
        load_migrations(directory)
    assert code(excinfo) == "MIGRATION_FILES_INVALID" and str(tmp_path) not in str(
        excinfo.value
    )


def test_a_missing_directory_is_a_safe_error(tmp_path: pathlib.Path) -> None:
    with pytest.raises(MigrationError) as excinfo:
        load_migrations(tmp_path / "nope")
    assert code(excinfo) == "MIGRATION_FILES_INVALID"


def test_a_locked_database_fails_safely_after_the_timeout(
    tmp_path: pathlib.Path,
) -> None:
    holder = file_db(tmp_path)
    apply_migrations(holder, load_migrations(MIGRATIONS), NOW)
    extra = Migration(
        2,
        "0002_extra",
        "CREATE TABLE extra (id INTEGER);",
        checksum("CREATE TABLE extra (id INTEGER);"),
    )
    holder.execute("BEGIN IMMEDIATE")  # another writer holds the lock
    blocked = file_db(tmp_path, timeout=0.05)
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(blocked, [*load_migrations(MIGRATIONS), extra], NOW)
    assert code(excinfo) == "MIGRATION_FAILED" and not blocked.in_transaction
    holder.execute("ROLLBACK")
    apply_migrations(
        blocked, [*load_migrations(MIGRATIONS), extra], NOW
    )  # the retry succeeds
    assert blocked.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 2


def test_concurrent_runners_apply_each_migration_exactly_once(
    tmp_path: pathlib.Path,
) -> None:
    migrations = load_migrations(MIGRATIONS)
    errors: list[BaseException] = []

    def run() -> None:
        conn = file_db(tmp_path, timeout=30)
        try:
            apply_migrations(conn, migrations, NOW)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=run) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    check = file_db(tmp_path)
    assert check.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    assert check.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_ledger_evidence_and_audit_records_are_immutable_by_trigger(
    tmp_path: pathlib.Path,
) -> None:
    conn = file_db(tmp_path)
    apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO accounts (account_id, customer_id, currency, eligibility_reference, status, created_at)"
        " VALUES ('a1', 'c1', 'USD', 'e1', 'open', ?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO movements (movement_id, account_id, movement_type, state, amount_cents, currency,"
        " created_at, updated_at) VALUES ('m1', 'a1', 'incoming_ach', 'settled', 500, 'USD', ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind, direction, amount_cents,"
        " authorized_caller_id, authorized_role, created_at)"
        " VALUES ('l1', 'a1', 'm1', 'incoming_settlement', 'credit', 500, 'c', 'payment_orchestrator', ?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind, occurred_at)"
        " VALUES ('ev1', 'm1', 'settlement', ?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO audit_trace (account_id, instruction_id, operation, outcome, caller_id, caller_role,"
        " correlation_id, occurred_at) VALUES ('a1', 'i1', 'op', 'accepted', 'c', 'r', 'corr', ?)",
        (NOW,),
    )
    for statement in (
        "UPDATE ledger_entries SET amount_cents = 1",
        "DELETE FROM ledger_entries",
        "UPDATE movement_evidence SET evidence_kind = 'return'",
        "DELETE FROM movement_evidence",
        "UPDATE audit_trace SET operation = 'x'",
        "DELETE FROM audit_trace",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable|not implemented"):
            conn.execute(statement)
    assert conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0] == 1


def test_a_trailing_comment_is_allowed(tmp_path: pathlib.Path) -> None:
    sql = b"CREATE TABLE a(x);\n-- done\n/* and that is all */\n"
    assert len(load_migrations(folder(tmp_path, {"0001_x.sql": sql}))) == 1


@pytest.mark.parametrize(
    "sql",
    [
        ";ROLLBACK;\nCREATE TABLE a(x);\nINSERT INTO nope VALUES(1);",
        ";COMMIT;\nCREATE TABLE a(x);\nINSERT INTO nope VALUES(1);",
        "﻿ROLLBACK;\nCREATE TABLE a(x);",
        "﻿COMMIT;\nCREATE TABLE a(x);",
        "CREATE TABLE a(x); COMMIT; CREATE TABLE b(y);",
        "CREATE TABLE a(x);\n;BEGIN;\nCREATE TABLE b(y);",
        "CREATE TABLE a(x);\nSAVEPOINT s;\nCREATE TABLE b(y);",
        "ATTACH DATABASE ':memory:' AS other;\nCREATE TABLE a(x);",
        "CREATE TABLE a(x);\nDETACH DATABASE main;",
        "PRAGMA writable_schema = ON;\nDELETE FROM sqlite_master;",
    ],
)
def test_transaction_control_can_not_slip_past_the_lexical_check(
    tmp_path: pathlib.Path, sql: str
) -> None:
    """Whatever the loader lets through, SQLite itself refuses and nothing is left behind."""
    conn = file_db(tmp_path)
    apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    before = list(conn.iterdump())
    bad = Migration(2, "0002_bad", sql, checksum(sql))
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [*load_migrations(MIGRATIONS), bad], NOW)
    assert code(excinfo) in {"MIGRATION_FAILED", "MIGRATION_FILES_INVALID"}
    assert not conn.in_transaction
    assert (
        list(conn.iterdump()) == before
    )  # no table, no history row, no partial change
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone() == (1,)
    # the authorizer is removed again, so the runner's own transaction control still works
    apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
