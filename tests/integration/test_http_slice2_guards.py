"""TASK-25 slice 2 guards: every operation refuses missing caller context, defaults hold, integers are canonical."""

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
from tests.integration.test_http_slice2 import CONTRACT_PATHS, RECON

PAYER = {
    "X-Caller-Id": "pay-1",
    "X-Caller-Role": "payment_orchestrator",
    "X-Correlation-Id": "corr-p",
}
READER = {
    "X-Caller-Id": "rd-1",
    "X-Caller-Role": "account_reader",
    "X-Correlation-Id": "corr-r",
    "X-Account-Scope": "acct-a",
}


@pytest.fixture
def client(tmp_path: pathlib.Path):
    started = start_database(
        tmp_path / "abm.sqlite3", MIGRATIONS, NOW, check_same_thread=False
    )
    assert started.connection is not None
    uow = SqliteUnitOfWork(started.connection)
    now = ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
    register(uow, now, "acct-a")
    register(uow, now, "acct-b")
    fund(uow, now, "acct-a", 500)
    with TestClient(create_app(uow, now), raise_server_exceptions=False) as test_client:
        yield test_client
    started.connection.close()


def concrete(path: str) -> str:
    return path.replace("{account_id}", "acct-a").replace("{movement_id}", "mv-x")


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(p for p in CONTRACT_PATHS if not p[1].startswith("/health")),
)
def test_every_operation_refuses_missing_caller_context_with_401(client, method, path):
    """Mutation evidence: removing the trusted-context check on any command route now fails here."""
    response = client.request(
        method, concrete(path), json={} if method == "POST" else None
    )
    assert response.status_code == 401, (method, path)
    assert (
        response.json()["ok"] is False
        and response.json()["error"]["code"] == "UNAUTHORIZED"
    )


@pytest.mark.parametrize(
    "raw",
    [
        (
            b'{"instruction_id": "ins-s", "movement_id": "mv-s", "source_account_id": "acct-a", '
            b'"destination_account_id": "acct-b", "amount_cents": 1, "amount_cents": 99, "currency": "USD"}'
        ),
        b"{not json",
    ],
    ids=["duplicate-key", "malformed"],
)
def test_transfer_body_is_parsed_strictly_before_any_money_moves(client, raw):
    before = client.get("/v1/accounts/acct-a/transactions", headers=READER).json()[
        "data"
    ]["items"]
    response = client.post(
        "/v1/transfers/internal",
        content=raw,
        headers={
            **PAYER,
            "Content-Type": "application/json",
            "Idempotency-Key": "k-strict",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    after = client.get("/v1/accounts/acct-a/transactions", headers=READER).json()[
        "data"
    ]["items"]
    assert after == before


def test_history_defaults_to_fifty_rows_per_page(client):
    for n in range(60):  # 60 one-cent transfers give 60 debit rows on acct-a
        response = client.post(
            "/v1/transfers/internal",
            json={
                "instruction_id": f"ins-d{n}",
                "movement_id": f"mv-d{n}",
                "source_account_id": "acct-a",
                "destination_account_id": "acct-b",
                "amount_cents": 1,
                "currency": "USD",
            },
            headers={**PAYER, "Idempotency-Key": f"k-d{n}"},
        )
        assert response.status_code == 201
    page = client.get("/v1/accounts/acct-a/transactions", headers=READER).json()
    assert len(page["data"]["items"]) == 50
    assert page["data"]["next_after_sequence"] is not None


def test_trace_defaults_to_one_hundred_rows_per_page(client):
    for n in range(60):
        client.post(
            "/v1/transfers/internal",
            json={
                "instruction_id": f"ins-t{n}",
                "movement_id": f"mv-t{n}",
                "source_account_id": "acct-a",
                "destination_account_id": "acct-b",
                "amount_cents": 1,
                "currency": "USD",
            },
            headers={**PAYER, "Idempotency-Key": f"k-t{n}"},
        )
    recon = {
        "X-Caller-Id": "recon-1",
        "X-Caller-Role": "reconciliation_reader",
        "X-Correlation-Id": "corr-t",
    }
    page = client.get("/v1/reconciliation/trace", headers=recon).json()
    assert len(page["data"]["items"]) == 100
    assert page["data"]["next_after_sequence"] is not None


@pytest.mark.parametrize(
    "path", ["/v1/accounts/acct-a/transactions", "/v1/reconciliation/trace"]
)
def test_an_integer_beyond_python_limits_is_a_validation_error(client, path):
    headers = READER if path.startswith("/v1/accounts") else RECON
    response = client.get(path + "?limit=" + "9" * 5000, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("value", ["1_0", "+1", "%201", "0x10", "1.0", " 1"])
def test_non_canonical_integers_are_validation_errors(client, value):
    response = client.get(
        f"/v1/accounts/acct-a/transactions?limit={value}", headers=READER
    )
    assert response.status_code == 400, value
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
