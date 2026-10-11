"""HTTP envelopes and trusted-context denial for registration and account read (TASK-25 slice 1; TEST-21, TEST-28, TEST-46 facets)."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from abm import main as http_module
from abm.api.http import STATUS_BY_CODE
from abm.domain.results import ERROR_CODES
from abm.main import create_app
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import MIGRATIONS, NOW, fund, register

ADMIN = {
    "X-Caller-Id": "registrar-1",
    "X-Caller-Role": "account_registrar",
    "X-Correlation-Id": "corr-1",
}
READER = {
    "X-Caller-Id": "rd-1",
    "X-Caller-Role": "account_reader",
    "X-Correlation-Id": "corr-r",
    "X-Account-Scope": "acct-a",
}
BODY = {
    "instruction_id": "ins-reg-h1",
    "account_id": "acct-h1",
    "customer_id": "cust-h1",
    "currency": "USD",
    "eligibility_reference": "elig-1",
}


@pytest.fixture
def client(tmp_path: pathlib.Path):
    started = start_database(
        tmp_path / "abm.sqlite3", MIGRATIONS, NOW, check_same_thread=False
    )
    assert started.connection is not None
    conn = started.connection
    uow = SqliteUnitOfWork(conn)
    now = ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
    register(uow, now, "acct-a")
    fund(uow, now, "acct-a", 500)
    app = create_app(uow, now)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client, conn
    conn.close()


def test_every_error_code_has_a_contract_status():
    assert set(STATUS_BY_CODE) == set(ERROR_CODES) - {"UNSUPPORTED_OPERATION"}


def test_missing_or_contradictory_caller_context_is_401_before_any_write(client):
    test_client, conn = client
    before = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    response = test_client.post(
        "/v1/accounts/registrations",
        json=BODY,
        headers={"Idempotency-Key": "k-h1"},  # no caller headers
    )
    assert response.status_code == 401
    assert (
        response.json()["ok"] is False
        and response.json()["error"]["code"] == "UNAUTHORIZED"
    )
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == before


def test_registration_returns_the_success_envelope_and_replays_exactly(client):
    test_client, _conn = client
    first = test_client.post(
        "/v1/accounts/registrations",
        json=BODY,
        headers={**ADMIN, "Idempotency-Key": "k-h1"},
    )
    assert first.status_code == 201
    body = first.json()
    assert body["ok"] is True and body["meta"] == {"correlation_id": "corr-1"}
    assert "replayed" not in body["meta"]

    replay = test_client.post(
        "/v1/accounts/registrations",
        json=BODY,
        headers={**ADMIN, "Idempotency-Key": "k-h1"},
    )
    assert replay.status_code == 201
    assert replay.json()["data"] == body["data"]
    assert replay.json()["meta"]["replayed"] is True


def test_malformed_json_is_a_validation_error_with_no_write(client):
    test_client, conn = client
    before = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    response = test_client.post(
        "/v1/accounts/registrations",
        content=b'{"instruction_id": ',
        headers={
            **ADMIN,
            "Idempotency-Key": "k-bad",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == before


def test_account_read_uses_the_trusted_scope_and_the_error_statuses(client):
    test_client, _conn = client
    ok = test_client.get("/v1/accounts/acct-a", headers=READER)
    assert ok.status_code == 200
    assert ok.json()["data"]["account_id"] == "acct-a"

    other = test_client.get("/v1/accounts/acct-b", headers=READER)
    assert (
        other.status_code == 403 and other.json()["error"]["code"] == "FORBIDDEN_SCOPE"
    )

    missing = test_client.get(
        "/v1/accounts/acct-zz", headers={**READER, "X-Account-Scope": "acct-zz"}
    )
    assert (
        missing.status_code == 404
        and missing.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
    )


def test_an_unexpected_exception_is_a_safe_internal_error_envelope(client, monkeypatch):
    test_client, _conn = client

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret detail: /internal/path SELECT * FROM accounts")

    monkeypatch.setattr(http_module, "get_account", boom)
    response = test_client.get(
        "/v1/accounts/acct-a", headers={**READER, "X-Correlation-Id": "corr-boom"}
    )
    assert response.status_code == 500
    payload = response.json()
    assert payload == {
        "ok": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "retryable": False,
        },
        "meta": {"correlation_id": "corr-boom"},
    }
    assert "secret" not in response.text and "SELECT" not in response.text


def test_an_invalid_correlation_id_is_replaced_by_the_fixed_value(client):
    test_client, _conn = client
    unauthorized = test_client.post(
        "/v1/accounts/registrations", json=BODY, headers={"X-Correlation-Id": "bad id"}
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json()["meta"] == {"correlation_id": "not-provided"}


def test_a_malformed_body_is_refused_before_the_caller_check(client):
    test_client, _conn = client
    response = test_client.post(
        "/v1/accounts/registrations",
        content=b"{not json",
        headers={"Content-Type": "application/json"},  # no caller headers as well
    )
    assert (
        response.status_code == 400
        and response.json()["error"]["code"] == "VALIDATION_ERROR"
    )
