"""TASK-17 Minor closure: every command route refuses missing caller context with 401, stores nothing, and
evaluates a same-key retry fresh once valid context is supplied (specs/04 section 4; TEST-15, TEST-46)."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from abm.application.authorization import PERMISSIONS, Operation
from abm.main import create_app
from abm.persistence.readiness import start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import MIGRATIONS, NOW, fund, register
from tests.integration.test_http_slice3 import COMMAND_ROUTES

# every POST command route of the contract: the slice-3 matrix routes plus account registration (API-01)
ROUTES = sorted(COMMAND_ROUTES.items()) + [("/v1/accounts/registrations", "API-01")]


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
    with TestClient(create_app(uow, now), raise_server_exceptions=False) as test_client:
        yield test_client, conn
    conn.close()


@pytest.mark.parametrize(("path", "api_id"), ROUTES)
def test_a_command_without_context_is_401_stores_nothing_and_a_retry_is_fresh(
    client, path, api_id
):
    test_client, conn = client
    key = f"k-401-{api_id}"
    role = next(r for r, ops in PERMISSIONS.items() if Operation(api_id) in ops)
    denied = test_client.post(path, json={}, headers={"Idempotency-Key": key})
    assert denied.status_code == 401, path
    assert denied.json()["error"]["code"] == "UNAUTHORIZED"
    stored = conn.execute(
        "SELECT COUNT(*) FROM idempotency_outcomes WHERE idempotency_key = ?", (key,)
    ).fetchone()[0]
    assert stored == 0, path

    # same key with valid context: evaluated afresh, so it is not the stored 401 and not a replay
    retry = test_client.post(
        path,
        json={},
        headers={
            "X-Caller-Id": f"c-{role}",
            "X-Caller-Role": role,
            "X-Correlation-Id": "corr-401",
            "X-Account-Scope": "acct-a",
            "Idempotency-Key": key,
        },
    )
    assert retry.status_code != 401, path
    assert retry.json().get("error", {}).get("code") != "UNAUTHORIZED", path
    assert "replayed" not in retry.json()["meta"], path
