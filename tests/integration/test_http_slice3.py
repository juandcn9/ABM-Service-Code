"""TASK-25 slice 3: health routes (API-20, API-21) and the remaining HTTP checks (TEST-20, TEST-22, TEST-23, TEST-24, TEST-26, TEST-30)."""

from __future__ import annotations

import pathlib
import re
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from abm.application.authorization import PERMISSIONS, Operation
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
RECON = {
    "X-Caller-Id": "recon-1",
    "X-Caller-Role": "reconciliation_reader",
    "X-Correlation-Id": "corr-t",
}

# POST command routes with the contract operation each one serves
COMMAND_ROUTES: dict[str, str] = {
    "/v1/accounts/acct-a/ach/incoming": "API-04",
    "/v1/accounts/acct-a/ach/incoming/mv-x/settlements": "API-05",
    "/v1/accounts/acct-a/ach/incoming/mv-x/returns": "API-06",
    "/v1/accounts/acct-a/ach/outgoing": "API-07",
    "/v1/accounts/acct-a/ach/outgoing/mv-x/submissions": "API-08",
    "/v1/accounts/acct-a/ach/outgoing/mv-x/settlements": "API-09",
    "/v1/accounts/acct-a/ach/outgoing/mv-x/rejections": "API-10",
    "/v1/accounts/acct-a/ach/outgoing/mv-x/cancellations": "API-11",
    "/v1/transfers/internal": "API-12",
    "/v1/accounts/acct-a/card-authorizations": "API-13",
    "/v1/accounts/acct-a/card-authorizations/mv-x/clearings": "API-14",
    "/v1/accounts/acct-a/card-authorizations/mv-x/reversals": "API-15",
    "/v1/accounts/acct-a/corrections": "API-16",
    "/v1/accounts/acct-a/risk-restrictions": "API-17",
    "/v1/accounts/acct-a/closure": "API-18",
    "/v1/accounts/acct-a/ach/outgoing/mv-x/returns": "API-22",
    "/v1/accounts/acct-a/card-authorizations/mv-x/expirations": "API-23",
    "/v1/accounts/acct-a/card-authorizations/mv-x/refunds": "API-24",
}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def make_client(tmp_path: pathlib.Path, readiness=None):
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
    client = TestClient(create_app(uow, now, readiness), raise_server_exceptions=False)
    return client, conn


# health (API-20, API-21)
def test_liveness_needs_no_context_and_reports_live(tmp_path):
    test_client, _conn = make_client(tmp_path)
    response = test_client.get("/health/live")
    assert response.status_code == 200 and response.json() == {"status": "live"}


def test_readiness_is_ready_when_the_check_is_clean(tmp_path):
    test_client, _conn = make_client(tmp_path, list)
    response = test_client.get("/health/ready")
    assert response.status_code == 200 and response.json() == {"status": "ready"}


def test_readiness_without_a_check_fails_closed(tmp_path):
    test_client, _conn = make_client(tmp_path)
    response = test_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unready",
        "reason_codes": ["DATABASE_UNAVAILABLE"],
    }


def test_a_raising_readiness_check_reports_only_a_safe_reason(tmp_path):
    def boom() -> list[str]:
        raise RuntimeError("path /secret/db.sqlite3 failed")

    test_client, _conn = make_client(tmp_path, boom)
    response = test_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unready",
        "reason_codes": ["DATABASE_UNAVAILABLE"],
    }
    assert "secret" not in response.text and "/db" not in response.text


def test_unknown_reason_codes_fail_closed_as_integrity_failed(tmp_path):
    test_client, _conn = make_client(
        tmp_path, lambda: ["BOGUS_CODE", "DATABASE_BUSY", "DATABASE_BUSY"]
    )
    response = test_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["reason_codes"] == ["DATABASE_BUSY", "INTEGRITY_FAILED"]


def test_readiness_reports_integrity_reason_codes_sorted(tmp_path):
    test_client, _conn = make_client(
        tmp_path, lambda: ["INTEGRITY_FAILED", "DATABASE_BUSY"]
    )
    response = test_client.get("/health/ready")
    assert response.json()["reason_codes"] == ["DATABASE_BUSY", "INTEGRITY_FAILED"]


# TEST-22: each role succeeds only on its matrix operations, refused with 403 elsewhere
@pytest.mark.parametrize(("path", "api_id"), sorted(COMMAND_ROUTES.items()))
def test_each_role_is_admitted_exactly_by_the_matrix(tmp_path, path, api_id):
    test_client, _conn = make_client(tmp_path)
    operation = Operation(api_id)
    allowed = {role for role, ops in PERMISSIONS.items() if operation in ops}
    assert allowed, api_id
    for role in PERMISSIONS:
        headers = {
            "X-Caller-Id": f"c-{role}",
            "X-Caller-Role": role,
            "X-Correlation-Id": "corr-m",
            "Idempotency-Key": f"k-{role}",
        }
        response = test_client.post(path, json={}, headers=headers)
        if role in allowed:
            assert response.status_code not in (401, 403), (role, api_id)
        else:
            assert response.status_code == 403, (role, api_id)
            assert response.json()["error"]["code"] == "FORBIDDEN_SCOPE"


# TEST-23: a movement of another account is refused exactly like a missing one, over HTTP
def test_a_foreign_movement_is_refused_exactly_like_a_missing_one(tmp_path):
    test_client, conn = make_client(tmp_path)
    notice = test_client.post(
        "/v1/accounts/acct-b/ach/incoming",
        json={
            "instruction_id": "ins-fb",
            "movement_id": "mv-fb",
            "amount_cents": 9,
            "currency": "USD",
            "external_reference": "ext-fb",
        },
        headers={**PAYER, "Idempotency-Key": "k-fb"},
    )
    assert notice.status_code == 201
    before = conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]
    foreign = test_client.post(
        "/v1/accounts/acct-a/ach/incoming/mv-fb/settlements",
        json={"instruction_id": "ins-x1", "evidence_reference": "ev-x1"},
        headers={**PAYER, "Idempotency-Key": "k-x1", "X-Correlation-Id": "corr-same"},
    )
    missing = test_client.post(
        "/v1/accounts/acct-a/ach/incoming/mv-nope/settlements",
        json={"instruction_id": "ins-x2", "evidence_reference": "ev-x2"},
        headers={**PAYER, "Idempotency-Key": "k-x2", "X-Correlation-Id": "corr-same"},
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"] == missing.json()["error"]
    assert conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0] == before


# TEST-24: identifiers are 1-128 URL-unreserved characters, and round-trip unchanged over HTTP
@pytest.mark.parametrize("account_id", ["acct%20x", "a" * 129, "acct+x", "%E2%82%AC"])
def test_malformed_identifiers_are_validation_errors(tmp_path, account_id):
    # a malformed identifier in the path is refused by validation; an invalid scope header would be 401
    test_client, _conn = make_client(tmp_path)
    response = test_client.get(
        f"/v1/accounts/{account_id}",
        headers={
            "X-Caller-Id": "rd-1",
            "X-Caller-Role": "account_reader",
            "X-Correlation-Id": "corr-r",
            "X-Account-Scope": "acct-a",
        },
    )
    assert (
        response.status_code == 400
        and response.json()["error"]["code"] == "VALIDATION_ERROR"
    )


def test_a_valid_identifier_round_trips_unchanged(tmp_path):
    test_client, _conn = make_client(tmp_path)
    account_id = "acct.A-1_~z"
    created = test_client.post(
        "/v1/accounts/registrations",
        json={
            "instruction_id": "ins-rt",
            "account_id": account_id,
            "customer_id": "cust-rt",
            "currency": "USD",
            "eligibility_reference": "elig-rt",
        },
        headers={
            "X-Caller-Id": "registrar-1",
            "X-Caller-Role": "account_registrar",
            "X-Correlation-Id": "corr-1",
            "Idempotency-Key": "k-rt",
        },
    )
    assert (
        created.status_code == 201
        and created.json()["data"]["account"]["account_id"] == account_id
    )
    read = test_client.get(
        f"/v1/accounts/{account_id}",
        headers={
            "X-Caller-Id": "rd-1",
            "X-Caller-Role": "account_reader",
            "X-Correlation-Id": "corr-r",
            "X-Account-Scope": account_id,
        },
    )
    assert read.json()["data"]["account_id"] == account_id


# TEST-30: no update or delete route exists on the retained records (method refusals)
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "path",
    [
        "/v1/accounts/acct-a/transactions",
        "/v1/reconciliation/trace",
        "/v1/accounts/acct-a/card-authorizations/mv-x/clearings",
    ],
)
def test_retained_records_have_no_update_or_delete_route(tmp_path, method, path):
    test_client, _conn = make_client(tmp_path)
    assert test_client.request(method, path, json={}).status_code == 405


# TEST-26: responses carry no e-mail address or prohibited field name (current application responses)
def test_responses_contain_no_email_address(tmp_path):
    test_client, _conn = make_client(tmp_path)
    bodies = [
        test_client.get(
            "/v1/accounts/acct-a",
            headers={
                "X-Caller-Id": "rd-1",
                "X-Caller-Role": "account_reader",
                "X-Correlation-Id": "corr-r",
                "X-Account-Scope": "acct-a",
            },
        ).text,
        test_client.get("/v1/reconciliation/trace", headers=RECON).text,
        test_client.get("/health/ready").text,
    ]
    for body in bodies:
        assert EMAIL.search(body) is None


# TEST-20: no route answers for an excluded operation; only the contract methods exist
def test_the_application_exposes_only_the_contract_methods(tmp_path):
    test_client, _conn = make_client(tmp_path)
    for path in (
        "/v1/accounts/acct-a/delete",
        "/v1/accounts/acct-a/reopen",
        "/v1/accounts/acct-a/adjust",
    ):
        assert test_client.post(path, json={}).status_code == 404
