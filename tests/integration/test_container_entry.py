"""TASK-27 composition root: the container entry point reads ABM_* only and reports real readiness."""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from abm.main import app_from_environment


def set_env(monkeypatch: pytest.MonkeyPatch, db: pathlib.Path) -> None:
    monkeypatch.setenv("ABM_MODE", "demonstration")
    monkeypatch.setenv("ABM_DB_PATH", str(db))
    monkeypatch.setenv("ABM_TRUSTED_INGRESS", "true")
    monkeypatch.delenv("ABM_CLOCK_MODE", raising=False)
    monkeypatch.delenv("ABM_LOG_LEVEL", raising=False)
    monkeypatch.delenv("ABM_BUSY_TIMEOUT_MS", raising=False)


def test_a_fresh_volume_reaches_ready(tmp_path, monkeypatch):
    set_env(monkeypatch, tmp_path / "abm.sqlite3")
    client = TestClient(app_from_environment())
    response = client.get("/health/ready")
    assert response.status_code == 200 and response.json() == {"status": "ready"}


def test_readiness_reflects_the_database_as_it_is_now(tmp_path, monkeypatch):
    # the check runs on each probe, not once at startup
    import sqlite3

    set_env(monkeypatch, tmp_path / "abm.sqlite3")
    client = TestClient(app_from_environment())
    assert client.get("/health/ready").status_code == 200
    conn = sqlite3.connect(tmp_path / "abm.sqlite3")
    conn.execute("DROP TABLE accounts")
    conn.commit()
    conn.close()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unready"


def test_an_unusable_path_starts_unready_with_a_safe_reason(tmp_path, monkeypatch):
    set_env(monkeypatch, tmp_path / "missing-dir" / "abm.sqlite3")
    client = TestClient(app_from_environment())
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unready",
        "reason_codes": ["DATABASE_UNAVAILABLE"],
    }
    # a write answers safely without touching a database (no partial effect)
    blocked = client.post(
        "/v1/accounts/registrations",
        json={
            "instruction_id": "ins-u",
            "account_id": "acct-u",
            "customer_id": "cust-u",
            "currency": "USD",
            "eligibility_reference": "elig-u",
        },
        headers={
            "X-Caller-Id": "reg-1",
            "X-Caller-Role": "account_registrar",
            "X-Correlation-Id": "corr-u",
            "Idempotency-Key": "k-1",
        },
    )
    assert blocked.status_code == 503
    assert blocked.json()["error"]["code"] == "SERVICE_UNREADY"


def test_a_bad_setting_refuses_to_start_and_names_only_the_setting(
    tmp_path, monkeypatch, capsys
):
    set_env(monkeypatch, tmp_path / "abm.sqlite3")
    monkeypatch.setenv("ABM_MODE", "not-a-mode-value")
    with pytest.raises(SystemExit) as info:
        app_from_environment()
    message = str(info.value)
    assert message == "CONFIG_INVALID: ABM_MODE"
    assert "not-a-mode-value" not in message


def test_reads_answer_service_unready_while_the_database_is_unusable(
    tmp_path, monkeypatch
):
    # TASK-27 F3: the same safe refusal on reads as on writes, with no data and no database access
    set_env(monkeypatch, tmp_path / "missing-dir" / "abm.sqlite3")
    client = TestClient(app_from_environment())
    reader = {
        "X-Caller-Id": "rd-1",
        "X-Caller-Role": "account_reader",
        "X-Correlation-Id": "corr-r",
        "X-Account-Scope": "acct-u",
    }
    recon = {
        "X-Caller-Id": "recon-1",
        "X-Caller-Role": "reconciliation_reader",
        "X-Correlation-Id": "corr-t",
    }
    for path, headers in [
        ("/v1/accounts/acct-u", reader),
        ("/v1/accounts/acct-u/transactions", reader),
        ("/v1/reconciliation/trace", recon),
    ]:
        response = client.get(path, headers=headers)
        assert response.status_code == 503, path
        assert response.json()["error"]["code"] == "SERVICE_UNREADY", path
        assert "data" not in response.json(), path


def _reasons_after(tmp_path, monkeypatch, tamper) -> list[str]:
    import sqlite3

    set_env(monkeypatch, tmp_path / "abm.sqlite3")
    TestClient(app_from_environment()).close()
    conn = sqlite3.connect(tmp_path / "abm.sqlite3")
    tamper(conn)
    conn.commit()
    conn.close()
    response = TestClient(app_from_environment()).get("/health/ready")
    assert response.status_code == 503
    return response.json()["reason_codes"]


def test_a_foreign_table_on_the_volume_starts_unready_as_integrity_failed(
    tmp_path, monkeypatch
):
    reasons = _reasons_after(
        tmp_path,
        monkeypatch,
        lambda conn: conn.execute("CREATE TABLE rogue (x INTEGER)"),
    )
    assert reasons == ["INTEGRITY_FAILED"]


def _alter_history(conn) -> None:
    # the history table is immutable by trigger; an operator who drops the guard can still edit it
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'schema_version'"
    ).fetchall():
        conn.execute(f'DROP TRIGGER "{name}"')
    conn.execute("UPDATE schema_version SET checksum = ?", ("0" * 64,))


def test_a_changed_migration_checksum_starts_unready_as_schema_unsupported(
    tmp_path, monkeypatch
):
    reasons = _reasons_after(
        tmp_path,
        monkeypatch,
        _alter_history,
    )
    assert reasons == ["SCHEMA_UNSUPPORTED"]
