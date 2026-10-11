"""HTTP routes for the remaining operations (TASK-25 slice 2): inventory, role checks, flows, unsupported methods."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from abm.main import create_app
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import MIGRATIONS, NOW, fund, register

PAYER = {
    "X-Caller-Id": "pay-1",
    "X-Caller-Role": "payment_orchestrator",
    "X-Correlation-Id": "corr-p",
}
CORRECTOR = {
    "X-Caller-Id": "corr-1",
    "X-Caller-Role": "correction_authority",
    "X-Correlation-Id": "corr-x",
}
RECON = {
    "X-Caller-Id": "recon-1",
    "X-Caller-Role": "reconciliation_reader",
    "X-Correlation-Id": "corr-t",
}
READER = {
    "X-Caller-Id": "rd-1",
    "X-Caller-Role": "account_reader",
    "X-Correlation-Id": "corr-r",
    "X-Account-Scope": "acct-a",
}
CONTRACT_PATHS = {
    ("POST", "/v1/accounts/registrations"),
    ("GET", "/v1/accounts/{account_id}"),
    ("GET", "/v1/accounts/{account_id}/transactions"),
    ("POST", "/v1/accounts/{account_id}/ach/incoming"),
    ("POST", "/v1/accounts/{account_id}/ach/incoming/{movement_id}/settlements"),
    ("POST", "/v1/accounts/{account_id}/ach/incoming/{movement_id}/returns"),
    ("POST", "/v1/accounts/{account_id}/ach/outgoing"),
    ("POST", "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/submissions"),
    ("POST", "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/settlements"),
    ("POST", "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/rejections"),
    ("POST", "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/cancellations"),
    ("POST", "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/returns"),
    ("POST", "/v1/transfers/internal"),
    ("POST", "/v1/accounts/{account_id}/card-authorizations"),
    ("POST", "/v1/accounts/{account_id}/card-authorizations/{movement_id}/clearings"),
    ("POST", "/v1/accounts/{account_id}/card-authorizations/{movement_id}/reversals"),
    ("POST", "/v1/accounts/{account_id}/card-authorizations/{movement_id}/expirations"),
    ("POST", "/v1/accounts/{account_id}/card-authorizations/{movement_id}/refunds"),
    ("POST", "/v1/accounts/{account_id}/corrections"),
    ("POST", "/v1/accounts/{account_id}/risk-restrictions"),
    ("POST", "/v1/accounts/{account_id}/closure"),
    ("GET", "/v1/reconciliation/trace"),
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
    register(uow, now, "acct-b")
    fund(uow, now, "acct-a", 500)
    with TestClient(create_app(uow, now), raise_server_exceptions=False) as test_client:
        yield test_client, conn
    conn.close()


def test_the_routes_are_exactly_the_contract_operations(client):
    test_client, _conn = client
    routes = {
        (method, route.path)
        for route in test_client.app.routes
        for method in getattr(route, "methods", set()) - {"HEAD"}
        if route.path.startswith("/v1/")
    }
    assert routes == CONTRACT_PATHS


def test_unsupported_methods_on_the_account_path_have_no_route(client):
    test_client, _conn = client
    assert test_client.put("/v1/accounts/acct-a", json={}).status_code == 405
    assert test_client.delete("/v1/accounts/acct-a").status_code == 405


def test_an_incoming_notice_then_settlement_over_http(client):
    test_client, conn = client
    notice = test_client.post(
        "/v1/accounts/acct-a/ach/incoming",
        json={
            "instruction_id": "ins-n1",
            "movement_id": "mv-n1",
            "amount_cents": 120,
            "currency": "USD",
            "external_reference": "ext-n1",
        },
        headers={**PAYER, "Idempotency-Key": "k-n1"},
    )
    assert notice.status_code == 201
    settled = test_client.post(
        "/v1/accounts/acct-a/ach/incoming/mv-n1/settlements",
        json={"instruction_id": "ins-s1", "evidence_reference": "ev-s1"},
        headers={**PAYER, "Idempotency-Key": "k-s1"},
    )
    assert settled.status_code == 200 and settled.json()["ok"] is True
    assert conn.execute(
        "SELECT current_balance_cents FROM accounts WHERE account_id = 'acct-a'"
    ).fetchone() == (620,)


def test_a_transfer_over_http_moves_the_funds(client):
    test_client, _conn = client
    response = test_client.post(
        "/v1/transfers/internal",
        json={
            "instruction_id": "ins-t1",
            "movement_id": "mv-t1",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": 50,
            "currency": "USD",
        },
        headers={**PAYER, "Idempotency-Key": "k-t1"},
    )
    assert response.status_code == 201
    assert response.json()["data"]["movement_type"] == "internal_transfer"


def test_a_role_outside_the_matrix_is_refused_over_http(client):
    test_client, conn = client
    before = conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0]
    response = test_client.post(
        "/v1/accounts/acct-a/corrections",
        json={
            "instruction_id": "ins-c1",
            "correction_id": "cor-1",
            "direction": "credit",
            "amount_cents": 10,
            "currency": "USD",
            "decision_reference": "dec-1",
        },
        headers={**PAYER, "Idempotency-Key": "k-c1"},
    )
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "FORBIDDEN_SCOPE"
    )
    assert conn.execute("SELECT COUNT(*) FROM audit_trace").fetchone()[0] == before


def test_the_trace_is_for_the_reconciliation_reader_only(client):
    test_client, _conn = client
    allowed = test_client.get("/v1/reconciliation/trace", headers=RECON)
    assert allowed.status_code == 200 and "items" in allowed.json()["data"]
    refused = test_client.get("/v1/reconciliation/trace", headers=READER)
    assert refused.status_code == 403


def test_history_paging_rejects_a_non_integer_limit(client):
    test_client, _conn = client
    ok = test_client.get("/v1/accounts/acct-a/transactions", headers=READER)
    assert ok.status_code == 200
    bad = test_client.get("/v1/accounts/acct-a/transactions?limit=abc", headers=READER)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_closed_account_refuses_new_instructions_over_http(client):
    test_client, _conn = client
    closed = test_client.post(
        "/v1/accounts/acct-b/closure",
        json={"instruction_id": "ins-close-b"},
        headers={
            "X-Caller-Id": "registrar-1",
            "X-Caller-Role": "account_registrar",
            "X-Correlation-Id": "corr-1",
            "Idempotency-Key": "k-close-b",
        },
    )
    assert closed.status_code == 200
    refused = test_client.post(
        "/v1/accounts/acct-b/ach/incoming",
        json={
            "instruction_id": "ins-n2",
            "movement_id": "mv-n2",
            "amount_cents": 10,
            "currency": "USD",
            "external_reference": "ext-n2",
        },
        headers={**PAYER, "Idempotency-Key": "k-n2"},
    )
    assert (
        refused.status_code == 422
        and refused.json()["error"]["code"] == "ACCOUNT_CLOSED"
    )
