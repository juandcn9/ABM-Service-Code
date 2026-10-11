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
