"""Migration runner against real SQLite (DEC-0007, INV-06, INV-18, DATA-01 through DATA-08)."""

from __future__ import annotations

import pathlib
import sqlite3

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
LATER = "2026-10-10T12:00:00Z"
# SHA-256 of contracts/sqlite-schema.sql at Specs v1.0.1 (5d1cd41); 0001 must equal the contract
CONTRACT_SHA256 = "dcf82d06040fac33b316f661d5adc71db110648b7aef7e9e2b73cb3d73069d02"
DATA_TABLES = {
    "accounts",
    "movements",
    "holds",
    "ledger_entries",
    "idempotency_outcomes",
    "audit_trace",
    "retention_metadata",
    "movement_evidence",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def make(version: int, name: str, sql: str) -> Migration:
    return Migration(version, name, sql, checksum(sql))


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {r[0] for r in rows if not r[0].startswith("sqlite_")}


def history(conn: sqlite3.Connection) -> list[tuple[int, str, str, str]]:
    return list(conn.execute("SELECT * FROM schema_version ORDER BY version"))


def code_of(excinfo: pytest.ExceptionInfo[MigrationError]) -> str:
    return excinfo.value.code


def test_first_migration_equals_the_schema_contract() -> None:
    sql = (MIGRATIONS / "0001_initial.sql").read_text(encoding="utf-8")
    assert checksum(sql) == CONTRACT_SHA256


def test_loads_the_repository_migrations_in_order() -> None:
    found = load_migrations(MIGRATIONS)
    assert [(m.version, m.name) for m in found] == [(1, "0001_initial")]
    assert found[0].checksum == CONTRACT_SHA256


def test_empty_database_converges_to_the_target_schema() -> None:
    conn = connect()
    apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    assert tables(conn) == DATA_TABLES | {"schema_version"}
    assert history(conn) == [(1, "0001_initial", CONTRACT_SHA256, NOW)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_rerun_is_a_no_op_and_keeps_the_original_applied_time() -> None:
    conn = connect()
    migrations = load_migrations(MIGRATIONS)
    apply_migrations(conn, migrations, NOW)
    apply_migrations(conn, migrations, LATER)
    assert history(conn) == [(1, "0001_initial", CONTRACT_SHA256, NOW)]


def test_pending_migrations_apply_forward_in_one_run() -> None:
    conn = connect()
    first = load_migrations(MIGRATIONS)
    apply_migrations(conn, first, NOW)
    second = make(2, "0002_extra", "CREATE TABLE extra (id INTEGER PRIMARY KEY);")
    apply_migrations(conn, [*first, second], LATER)
    assert "extra" in tables(conn)
    assert [row[:2] for row in history(conn)] == [
        (1, "0001_initial"),
        (2, "0002_extra"),
    ]
    assert history(conn)[1][3] == LATER


def test_edited_applied_migration_is_refused_without_changes() -> None:
    conn = connect()
    apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    before = history(conn)
    edited = make(1, "0001_initial", "CREATE TABLE evil (id INTEGER);")
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [edited], LATER)
    assert code_of(excinfo) == "MIGRATION_CHECKSUM_MISMATCH"
    assert history(conn) == before
    assert "evil" not in tables(conn)


def test_renamed_applied_migration_is_refused() -> None:
    conn = connect()
    original = load_migrations(MIGRATIONS)[0]
    apply_migrations(conn, [original], NOW)
    renamed = Migration(1, "0001_renamed", original.sql, original.checksum)
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [renamed], LATER)
    assert code_of(excinfo) == "MIGRATION_CHECKSUM_MISMATCH"


def test_database_newer_than_this_build_is_unsupported() -> None:
    conn = connect()
    migrations = load_migrations(MIGRATIONS)
    apply_migrations(conn, migrations, NOW)
    conn.execute(
        "INSERT INTO schema_version VALUES (2, '0002_future', ?, ?)", ("a" * 64, NOW)
    )
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, migrations, LATER)
    assert code_of(excinfo) == "UNSUPPORTED_SCHEMA_VERSION"


def test_populated_database_without_history_is_left_untouched() -> None:
    conn = connect()
    conn.execute("CREATE TABLE foreign_data (id INTEGER)")
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    assert code_of(excinfo) == "UNSUPPORTED_SCHEMA_VERSION"
    assert tables(conn) == {"foreign_data"}


def test_failure_rolls_back_every_pending_migration() -> None:
    conn = connect()
    bad = make(2, "0002_bad", "CREATE TABLE t (a);\nINSERT INTO nope VALUES (1);")
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [*load_migrations(MIGRATIONS), bad], NOW)
    assert code_of(excinfo) == "MIGRATION_FAILED"
    assert tables(conn) == set()  # the valid 0001 was rolled back with the failing 0002
    assert not conn.in_transaction


def test_failure_after_an_applied_version_keeps_that_version_only() -> None:
    conn = connect()
    first = load_migrations(MIGRATIONS)
    apply_migrations(conn, first, NOW)
    bad = make(2, "0002_bad", "CREATE TABLE t (a);\nINSERT INTO nope VALUES (1);")
    with pytest.raises(MigrationError):
        apply_migrations(conn, [*first, bad], LATER)
    assert "t" not in tables(conn)
    assert [row[0] for row in history(conn)] == [1]


def test_error_exposes_only_a_safe_code() -> None:
    conn = connect()
    bad = make(1, "0001_bad", "INSERT INTO secret_table_name VALUES ('x');")
    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(conn, [bad], NOW)
    assert str(excinfo.value) == "MIGRATION_FAILED"
    assert "secret_table_name" not in str(excinfo.value)


def test_runner_requires_an_autocommit_connection() -> None:
    conn = sqlite3.connect(":memory:")  # default isolation level
    with pytest.raises(MigrationError):
        apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    conn = connect()
    conn.execute("BEGIN")
    with pytest.raises(MigrationError):
        apply_migrations(conn, load_migrations(MIGRATIONS), NOW)


def test_loader_rejects_gaps_duplicates_and_bad_names(tmp_path: pathlib.Path) -> None:
    def folder(*names: str) -> pathlib.Path:
        d = tmp_path / str(len(list(tmp_path.iterdir())))
        d.mkdir()
        for n in names:
            (d / n).write_text("SELECT 1;", encoding="utf-8")
        return d

    assert [m.version for m in load_migrations(folder("0001_a.sql", "0002_b.sql"))] == [
        1,
        2,
    ]
    for bad in (
        ("0002_a.sql",),  # does not start at 1
        ("0001_a.sql", "0003_c.sql"),  # gap
        ("0001_a.sql", "0001_b.sql"),  # duplicate version
        ("001_a.sql",),  # malformed version
        ("0001_bad name.sql",),  # name outside the stored alphabet
        ("0001.sql",),  # no name
    ):
        with pytest.raises(MigrationError) as excinfo:
            load_migrations(folder(*bad))
        assert code_of(excinfo) == "MIGRATION_FILES_INVALID", bad


def test_checksum_ignores_line_ending_style() -> None:
    assert checksum("a\r\nb\r\n") == checksum("a\nb\n")


def test_history_and_ledger_are_immutable_in_the_schema() -> None:
    conn = connect()
    apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE schema_version SET checksum = ?", ("b" * 64,))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("DELETE FROM schema_version")


def test_schema_enforces_core_money_constraints() -> None:
    conn = connect()
    apply_migrations(conn, load_migrations(MIGRATIONS), NOW)
    account = ("acct-1", "cust-1", "USD", "elig-1", "open", NOW)
    insert = (
        "INSERT INTO accounts (account_id, customer_id, currency, eligibility_reference,"
        " status, created_at) VALUES (?, ?, ?, ?, ?, ?)"
    )
    conn.execute(insert, account)
    with pytest.raises(sqlite3.IntegrityError):  # unique customer/account mapping
        conn.execute(insert, ("acct-2", "cust-1", "USD", "elig-2", "open", NOW))
    with pytest.raises(sqlite3.IntegrityError):  # USD only
        conn.execute(insert, ("acct-3", "cust-3", "EUR", "elig-3", "open", NOW))
    with pytest.raises(sqlite3.IntegrityError):  # opaque identifier alphabet
        conn.execute(insert, ("bad id", "cust-4", "USD", "elig-4", "open", NOW))
    with pytest.raises(sqlite3.IntegrityError):  # money magnitudes are positive
        conn.execute(
            "INSERT INTO movements (movement_id, account_id, movement_type, state,"
            " amount_cents, currency, created_at, updated_at)"
            " VALUES ('m-1', 'acct-1', 'card', 'pending', 0, 'USD', ?, ?)",
            (NOW, NOW),
        )


def test_unexpected_exception_still_rolls_back_and_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_sql: str) -> object:
        raise RuntimeError("unexpected")

    migrations = load_migrations(MIGRATIONS)
    monkeypatch.setattr("abm.persistence.migrations._statements", boom)
    conn = connect()
    with pytest.raises(RuntimeError):
        apply_migrations(conn, migrations, NOW)
    assert not conn.in_transaction
    assert tables(conn) == set()


def test_two_statements_on_one_line_both_apply() -> None:
    conn = connect()
    one_line = make(2, "0002_one_line", "CREATE TABLE a (x); CREATE TABLE b (y);")
    apply_migrations(conn, [*load_migrations(MIGRATIONS), one_line], NOW)
    assert {"a", "b"} <= tables(conn)
