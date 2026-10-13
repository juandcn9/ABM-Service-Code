"""TASK-36: the smoke probes pass against the real entry point, and a wrong status is reported by name."""

from __future__ import annotations

import pathlib
import sys

import pytest
from starlette.testclient import TestClient

from abm.main import app_from_environment

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from smoke_container import run_smoke  # type: ignore[import-not-found]


def set_env(monkeypatch: pytest.MonkeyPatch, db: pathlib.Path) -> None:
    monkeypatch.setenv("ABM_MODE", "demonstration")
    monkeypatch.setenv("ABM_DB_PATH", str(db))
    monkeypatch.setenv("ABM_TRUSTED_INGRESS", "true")
    monkeypatch.delenv("ABM_CLOCK_MODE", raising=False)


def adapter(client: TestClient, broken_path: str | None = None):
    def call(method, path, body, headers):
        response = client.request(method, path, json=body, headers=headers)
        status = response.status_code
        if path == broken_path:
            status = (
                599  # a deliberately wrong status, to prove the report names the probe
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return status, payload

    return call


def test_every_probe_passes_against_the_entry_point(tmp_path, monkeypatch):
    set_env(monkeypatch, tmp_path / "smoke.sqlite3")
    client = TestClient(app_from_environment())
    assert run_smoke(adapter(client)) == []


def test_a_wrong_status_is_reported_by_name(tmp_path, monkeypatch):
    set_env(monkeypatch, tmp_path / "smoke-broken.sqlite3")
    client = TestClient(app_from_environment())
    failures = run_smoke(adapter(client, broken_path="/health/live"))
    assert failures == ["liveness: expected HTTP 200, got 599"]


def leaking(client: TestClient, effect):
    """The adapter, except that the denied registration (payment role) also performs `effect`, as a
    broken entry point would: a state change behind a refusal. The effect uses the public API."""
    base = adapter(client)

    def call(method, path, body, headers):
        result = base(method, path, body, headers)
        if (
            method == "POST"
            and path == "/v1/accounts/registrations"
            and headers.get("X-Caller-Role") == "payment_orchestrator"
        ):
            effect(client)
        return result

    return call


def credit_acct_smoke(client: TestClient) -> None:
    # a real 50-cent credit to the smoke account (notice then settlement) through the public API
    pay = {
        "X-Caller-Id": "leak-pay",
        "X-Caller-Role": "payment_orchestrator",
        "X-Correlation-Id": "leak-c",
    }
    notice = {
        "instruction_id": "leak-ins-1",
        "movement_id": "leak-mv-1",
        "amount_cents": 50,
        "currency": "USD",
        "external_reference": "leak-ext-1",
    }
    client.post(
        "/v1/accounts/acct-smoke/ach/incoming",
        json=notice,
        headers={**pay, "Idempotency-Key": "leak-k-notice"},
    )
    client.post(
        "/v1/accounts/acct-smoke/ach/incoming/leak-mv-1/settlements",
        json={"instruction_id": "leak-set-1", "evidence_reference": "leak-ev-1"},
        headers={**pay, "Idempotency-Key": "leak-k-settle"},
    )


def register_acct_denied(client: TestClient) -> None:
    # an account created behind the refused registration
    client.post(
        "/v1/accounts/registrations",
        json={
            "instruction_id": "leak-reg-1",
            "account_id": "acct-denied",
            "customer_id": "cust-leak",
            "currency": "USD",
            "eligibility_reference": "elig-leak",
        },
        headers={
            "X-Caller-Id": "leak-reg",
            "X-Caller-Role": "account_registrar",
            "X-Correlation-Id": "leak-r",
            "Idempotency-Key": "leak-k-reg",
        },
    )


def test_a_denied_call_that_moves_money_is_reported(tmp_path, monkeypatch):
    # TASK-36 F2, mutant m1: the denied-balance check must report a balance changed by a refusal
    set_env(monkeypatch, tmp_path / "smoke-leak-balance.sqlite3")
    client = TestClient(app_from_environment())
    failures = run_smoke(leaking(client, credit_acct_smoke))
    assert any("denied requests changed the balance" in f for f in failures), failures


def test_a_denied_call_that_creates_an_account_is_reported(tmp_path, monkeypatch):
    # TASK-36 F2, mutant m4: the denied-account check must report an account left behind by a refusal
    set_env(monkeypatch, tmp_path / "smoke-leak-account.sqlite3")
    client = TestClient(app_from_environment())
    failures = run_smoke(leaking(client, register_acct_denied))
    assert any("denied registration left an account behind" in f for f in failures), (
        failures
    )
