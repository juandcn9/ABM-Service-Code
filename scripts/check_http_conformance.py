"""TEST-46 conformance: every response of the HTTP binding matches the contract (TASK-25).

Usage (from the repository root):  python scripts/check_http_conformance.py PATH_TO_openapi.yaml

For each contract operation it sends a probe that is always answered (no caller context, which must
give 401; and, where the contract declares 404 or 400, a deterministic probe that gives it). Each
response must use a status the contract declares for that operation, and its JSON body must match the
declared schema for that status. Success bodies are probed for registration, account read, history,
trace, and health. Exit status 0 means no deviation was found. The contract is read as JSON, which
the Specs publish; no third-party parser is used.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from datetime import UTC, datetime
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from schema_lite import check  # type: ignore[import-not-found]
from starlette.testclient import TestClient

from abm.main import create_app
from abm.persistence.readiness import readiness_reasons, start_database
from abm.persistence.sqlite_store import SqliteUnitOfWork
from harness.clock import ControllableClock
from tests.integration.store_support import (
    MIGRATIONS,
    NOW,
    fund,
    register,
)

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
RECON = {
    "X-Caller-Id": "recon-1",
    "X-Caller-Role": "reconciliation_reader",
    "X-Correlation-Id": "corr-t",
}


def _concrete(path: str) -> str:
    return path.replace("{account_id}", "acct-a").replace("{movement_id}", "mv-x")


def _declared(contract: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    return contract["paths"][path][method.lower()]


def _check_response(
    contract: dict[str, Any],
    path: str,
    method: str,
    status: int,
    body: Any,
    failures: list[str],
    label: str,
) -> None:
    operation = _declared(contract, path, method)
    declared = operation.get("responses", {})
    if str(status) not in declared:
        failures.append(
            f"{label}: status {status} is not declared ({sorted(declared)})"
        )
        return
    schema = (
        declared[str(status)]
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    if schema is None:
        if status == 200 or status == 201:
            failures.append(f"{label}: no JSON schema declared for {status}")
        return
    try:
        errors = check(body, schema, contract)
    except Exception as exc:  # noqa: BLE001  # the checker refuses an unsupported construct; a finding
        failures.append(f"{label}: checker error {exc}")
        return
    for error in errors:
        failures.append(f"{label}: {error}")


def main(contract_path: pathlib.Path) -> int:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    started = start_database(
        pathlib.Path(tempfile.mkdtemp()) / "conf.sqlite3",
        MIGRATIONS,
        NOW,
        check_same_thread=False,
    )
    conn = started.connection
    assert conn is not None
    uow = SqliteUnitOfWork(conn)
    clock = ControllableClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
    register(uow, clock, "acct-a")
    register(uow, clock, "acct-b")
    fund(uow, clock, "acct-a", 500)
    client = TestClient(
        create_app(uow, clock, lambda: readiness_reasons(conn, MIGRATIONS)),
        raise_server_exceptions=False,
    )
    failures: list[str] = []
    checked = 0
    for path, methods in contract["paths"].items():
        for method in methods:
            if method.upper() not in ("GET", "POST"):
                continue
            label = f"{method.upper()} {path}"
            probe = _concrete(path)
            if path.startswith("/health"):
                response = client.request(method.upper(), probe)
                checked += 1
                _check_response(
                    contract,
                    path,
                    method,
                    response.status_code,
                    response.json(),
                    failures,
                    label,
                )
                continue
            # 401: no caller context at all
            response = client.request(
                method.upper(), probe, json={} if method == "post" else None
            )
            checked += 1
            _check_response(
                contract,
                path,
                method,
                response.status_code,
                response.json(),
                failures,
                f"{label} [no context]",
            )
            # 403: a role outside the matrix (reader on a command, payer on a read)
            if method == "post" or "transactions" in path:
                role_headers = PAYER if method == "post" else READER
                response = client.request(
                    method.upper(),
                    probe,
                    json={} if method == "post" else None,
                    headers={**role_headers, "Idempotency-Key": "k-conf"},
                )
                checked += 1
                _check_response(
                    contract,
                    path,
                    method,
                    response.status_code,
                    response.json(),
                    failures,
                    f"{label} [role]",
                )
    # 400: a malformed JSON body with caller context, refused by schema before the context check
    # 404: an unknown account in the path, with a scope that matches it
    for path, methods in contract["paths"].items():
        for method in methods:
            if method.upper() == "POST" and not path.startswith("/health"):
                response = client.request(
                    "POST",
                    _concrete(path),
                    content=b"{not json",
                    headers={
                        **PAYER,
                        "Idempotency-Key": "k-400",
                        "Content-Type": "application/json",
                    },
                )
                checked += 1
                _check_response(
                    contract,
                    path,
                    method,
                    response.status_code,
                    response.json(),
                    failures,
                    f"POST {path} [malformed body]",
                )
    unknown = {**READER, "X-Account-Scope": "acct-zz"}
    response = client.get("/v1/accounts/acct-zz", headers=unknown)
    checked += 1
    _check_response(
        contract,
        "/v1/accounts/{account_id}",
        "get",
        response.status_code,
        response.json(),
        failures,
        "GET /v1/accounts/{account_id} [unknown account]",
    )
    # success bodies that the contract defines and the probes above can reach
    ok_cases = [
        (
            "post",
            "/v1/accounts/registrations",
            {
                "instruction_id": "ins-conf-r",
                "account_id": "acct-c",
                "customer_id": "cust-c",
                "currency": "USD",
                "eligibility_reference": "elig-c",
            },
            {
                "X-Caller-Id": "registrar-1",
                "X-Caller-Role": "account_registrar",
                "X-Correlation-Id": "corr-1",
                "Idempotency-Key": "k-conf-r",
            },
        ),
        (
            "get",
            "/v1/accounts/{account_id}",
            None,
            {**READER, "X-Account-Scope": "acct-a"},
        ),
        ("get", "/v1/accounts/{account_id}/transactions", None, READER),
        ("get", "/v1/reconciliation/trace", None, RECON),
    ]
    for method, path, body, headers in ok_cases:
        response = client.request(
            method.upper(), _concrete(path), json=body, headers=headers
        )
        checked += 1
        _check_response(
            contract,
            path,
            method,
            response.status_code,
            response.json(),
            failures,
            f"{method.upper()} {path} [success]",
        )
    print(f"probed {checked} responses across {len(contract['paths'])} paths")
    for failure in failures:
        print("DEVIATION", failure)
    print("PASS" if not failures else f"FAIL: {len(failures)} deviation(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: check_http_conformance.py PATH_TO_openapi.yaml")
        sys.exit(2)
    sys.exit(main(pathlib.Path(sys.argv[1])))
