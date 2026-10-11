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
        if response.status_code >= 300:
            failures.append(
                method.upper()
                + " "
                + path
                + " [success probe] refused with "
                + str(response.status_code)
            )
        _check_response(
            contract,
            path,
            method,
            response.status_code,
            response.json(),
            failures,
            f"{method.upper()} {path} [success]",
        )
    checked += _success_flows(client, contract, failures)
    print(f"probed {checked} responses across {len(contract['paths'])} paths")
    for failure in failures:
        print("DEVIATION", failure)
    print("PASS" if not failures else f"FAIL: {len(failures)} deviation(s)")
    return 0 if not failures else 1


REGISTRAR = {
    "X-Caller-Id": "registrar-1",
    "X-Caller-Role": "account_registrar",
    "X-Correlation-Id": "corr-1",
}
CARD = {
    "X-Caller-Id": "card-1",
    "X-Caller-Role": "card_orchestrator",
    "X-Correlation-Id": "corr-c",
}
RISK = {
    "X-Caller-Id": "risk-1",
    "X-Caller-Role": "risk_controller",
    "X-Correlation-Id": "corr-r",
}
CORRECTOR = {
    "X-Caller-Id": "corr-1",
    "X-Caller-Role": "correction_authority",
    "X-Correlation-Id": "corr-x",
}


def _success_flows(
    client: TestClient, contract: dict[str, Any], failures: list[str]
) -> int:
    """Success probes for the operations not covered above, through real business flows (TEST-46).

    Each step calls its operation's own path, expects a declared status, and checks the body against
    the declared schema. acct-a carries funds; acct-b receives a transfer and a restriction; acct-f-c is
    a fresh zero-balance account that is closed last.
    """
    count = 0
    counter = [0]

    def step(
        method: str, template: str, concrete: str, body: Any, headers: dict[str, str]
    ) -> None:
        nonlocal count
        counter[0] += 1
        key = "k-flow-" + str(counter[0])
        response = client.request(
            method, concrete, json=body, headers={**headers, "Idempotency-Key": key}
        )
        count += 1
        if response.status_code >= 300:
            failures.append(
                method
                + " "
                + template
                + " [success flow] refused with "
                + str(response.status_code)
                + " "
                + str(response.json().get("error", {}).get("code"))
            )
        _check_response(
            contract,
            template,
            method.lower(),
            response.status_code,
            response.json(),
            failures,
            method + " " + template + " [success flow]",
        )

    def ach(extra: str) -> str:
        return "/v1/accounts/acct-a/ach/" + extra

    card = "/v1/accounts/acct-a/card-authorizations"
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/incoming",
        ach("incoming"),
        {
            "instruction_id": "ins-f-in",
            "movement_id": "mv-f-in",
            "amount_cents": 50,
            "currency": "USD",
            "external_reference": "ext-f-in",
        },
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/incoming/{movement_id}/settlements",
        ach("incoming/mv-f-in/settlements"),
        {"instruction_id": "ins-f-in-s", "evidence_reference": "ev-f-in-s"},
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/incoming/{movement_id}/returns",
        ach("incoming/mv-f-in/returns"),
        {
            "instruction_id": "ins-f-in-r",
            "evidence_reference": "ev-f-in-r",
            "amount_cents": 50,
            "currency": "USD",
        },
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing",
        ach("outgoing"),
        {
            "instruction_id": "ins-f-o",
            "movement_id": "mv-f-o",
            "amount_cents": 40,
            "currency": "USD",
            "external_reference": "ext-f-o",
            "destination_reference": "dest-f",
        },
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/submissions",
        ach("outgoing/mv-f-o/submissions"),
        {"instruction_id": "ins-f-o-sub", "evidence_reference": "ev-f-o-sub"},
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/settlements",
        ach("outgoing/mv-f-o/settlements"),
        {"instruction_id": "ins-f-o-set", "evidence_reference": "ev-f-o-set"},
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/returns",
        ach("outgoing/mv-f-o/returns"),
        {
            "instruction_id": "ins-f-o-ret",
            "evidence_reference": "ev-f-o-ret",
            "amount_cents": 40,
            "currency": "USD",
        },
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing",
        ach("outgoing"),
        {
            "instruction_id": "ins-f-r",
            "movement_id": "mv-f-r",
            "amount_cents": 15,
            "currency": "USD",
            "external_reference": "ext-f-r",
            "destination_reference": "dest-f",
        },
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/submissions",
        ach("outgoing/mv-f-r/submissions"),
        {"instruction_id": "ins-f-r-sub", "evidence_reference": "ev-f-r-sub"},
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/rejections",
        ach("outgoing/mv-f-r/rejections"),
        {"instruction_id": "ins-f-r-rej", "evidence_reference": "ev-f-r-rej"},
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing",
        ach("outgoing"),
        {
            "instruction_id": "ins-f-c",
            "movement_id": "mv-f-c",
            "amount_cents": 15,
            "currency": "USD",
            "external_reference": "ext-f-c",
            "destination_reference": "dest-f",
        },
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/ach/outgoing/{movement_id}/cancellations",
        ach("outgoing/mv-f-c/cancellations"),
        {"instruction_id": "ins-f-c-can", "evidence_reference": "ev-f-c-can"},
        PAYER,
    )
    step(
        "POST",
        "/v1/transfers/internal",
        "/v1/transfers/internal",
        {
            "instruction_id": "ins-f-t",
            "movement_id": "mv-f-t",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": 10,
            "currency": "USD",
        },
        PAYER,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/card-authorizations",
        card,
        {
            "instruction_id": "ins-f-ca",
            "movement_id": "mv-f-ca",
            "amount_cents": 30,
            "currency": "USD",
            "external_reference": "ext-f-ca",
            "merchant_reference": "m-f",
        },
        CARD,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/clearings",
        card + "/mv-f-ca/clearings",
        {
            "instruction_id": "ins-f-cc",
            "evidence_reference": "ev-f-cc",
            "amount_cents": 30,
            "currency": "USD",
        },
        CARD,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/refunds",
        card + "/mv-f-ca/refunds",
        {
            "instruction_id": "ins-f-cr",
            "evidence_reference": "ev-f-cr",
            "amount_cents": 30,
            "currency": "USD",
        },
        CARD,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/card-authorizations",
        card,
        {
            "instruction_id": "ins-f-cv",
            "movement_id": "mv-f-cv",
            "amount_cents": 20,
            "currency": "USD",
            "external_reference": "ext-f-cv",
            "merchant_reference": "m-f",
        },
        CARD,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/reversals",
        card + "/mv-f-cv/reversals",
        {"instruction_id": "ins-f-cv-r", "evidence_reference": "ev-f-cv-r"},
        CARD,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/card-authorizations",
        card,
        {
            "instruction_id": "ins-f-ce",
            "movement_id": "mv-f-ce",
            "amount_cents": 20,
            "currency": "USD",
            "external_reference": "ext-f-ce",
            "merchant_reference": "m-f",
        },
        CARD,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/card-authorizations/{movement_id}/expirations",
        card + "/mv-f-ce/expirations",
        {"instruction_id": "ins-f-ce-x", "evidence_reference": "ev-f-ce-x"},
        CARD,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/corrections",
        "/v1/accounts/acct-a/corrections",
        {
            "instruction_id": "ins-f-cor",
            "correction_id": "cor-f",
            "direction": "credit",
            "amount_cents": 5,
            "currency": "USD",
            "decision_reference": "dec-f-cor",
        },
        CORRECTOR,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/risk-restrictions",
        "/v1/accounts/acct-b/risk-restrictions",
        {
            "instruction_id": "ins-f-risk",
            "action": "set",
            "decision_reference": "dec-f-risk",
        },
        RISK,
    )
    step(
        "POST",
        "/v1/accounts/registrations",
        "/v1/accounts/registrations",
        {
            "instruction_id": "ins-f-reg-c",
            "account_id": "acct-f-c",
            "customer_id": "cust-f-c",
            "currency": "USD",
            "eligibility_reference": "elig-f-c",
        },
        REGISTRAR,
    )
    step(
        "POST",
        "/v1/accounts/{account_id}/closure",
        "/v1/accounts/acct-f-c/closure",
        {"instruction_id": "ins-f-close"},
        REGISTRAR,
    )
    return count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: check_http_conformance.py PATH_TO_openapi.yaml")
        sys.exit(2)
    sys.exit(main(pathlib.Path(sys.argv[1])))
