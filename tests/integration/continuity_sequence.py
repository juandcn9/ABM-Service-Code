"""TASK-28 shared sequence: the Specs section 5 restart flows, driven over HTTP on the real entry point.

Used by tests/integration/test_restart_continuity.py in-process and by its killed subprocess. Each step
is (name, method, path, json body, headers, expected status). Steps run in this order and each one
commits its own write transaction.
"""

from __future__ import annotations

import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

REGISTRAR = {
    "X-Caller-Id": "reg-1",
    "X-Caller-Role": "account_registrar",
    "X-Correlation-Id": "corr-reg",
}
PAYER = {
    "X-Caller-Id": "pay-1",
    "X-Caller-Role": "payment_orchestrator",
    "X-Correlation-Id": "corr-p",
}
CARD = {
    "X-Caller-Id": "card-1",
    "X-Caller-Role": "card_orchestrator",
    "X-Correlation-Id": "corr-c",
}
RISK = {
    "X-Caller-Id": "risk-1",
    "X-Caller-Role": "risk_controller",
    "X-Correlation-Id": "corr-k",
}
CORRECTOR = {
    "X-Caller-Id": "corr-1",
    "X-Caller-Role": "correction_authority",
    "X-Correlation-Id": "corr-x",
}


def key(headers: dict[str, str], name: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": name}


def reg(account: str, instruction: str) -> dict[str, Any]:
    return {
        "instruction_id": instruction,
        "account_id": account,
        "customer_id": f"cust-{account}",
        "currency": "USD",
        "eligibility_reference": f"elig-{account}",
    }


STEPS: list[tuple[str, str, str, Any, dict[str, str], int]] = [
    (
        "register acct-a",
        "POST",
        "/v1/accounts/registrations",
        reg("acct-a", "ins-reg-a"),
        key(REGISTRAR, "k-reg-a"),
        201,
    ),
    (
        "register acct-b",
        "POST",
        "/v1/accounts/registrations",
        reg("acct-b", "ins-reg-b"),
        key(REGISTRAR, "k-reg-b"),
        201,
    ),
    (
        "incoming notice",
        "POST",
        "/v1/accounts/acct-a/ach/incoming",
        {
            "instruction_id": "ins-n1",
            "movement_id": "mv-n1",
            "amount_cents": 1000,
            "currency": "USD",
            "external_reference": "ext-n1",
        },
        key(PAYER, "k-n1"),
        201,
    ),
    (
        "incoming settlement",
        "POST",
        "/v1/accounts/acct-a/ach/incoming/mv-n1/settlements",
        {"instruction_id": "ins-s1", "evidence_reference": "ev-s1"},
        key(PAYER, "k-s1"),
        200,
    ),
    (
        "internal transfer",
        "POST",
        "/v1/transfers/internal",
        {
            "instruction_id": "ins-t1",
            "movement_id": "mv-t1",
            "source_account_id": "acct-a",
            "destination_account_id": "acct-b",
            "amount_cents": 50,
            "currency": "USD",
        },
        key(PAYER, "k-t1"),
        201,
    ),
    (
        "outgoing create",
        "POST",
        "/v1/accounts/acct-a/ach/outgoing",
        {
            "instruction_id": "ins-o1",
            "movement_id": "mv-o1",
            "amount_cents": 200,
            "currency": "USD",
            "external_reference": "ext-o1",
            "destination_reference": "dest-1",
        },
        key(PAYER, "k-o1"),
        201,
    ),
    (
        "outgoing submission",
        "POST",
        "/v1/accounts/acct-a/ach/outgoing/mv-o1/submissions",
        {"instruction_id": "ins-o1s", "evidence_reference": "ev-o1s"},
        key(PAYER, "k-o1s"),
        200,
    ),
    (
        "outgoing settlement",
        "POST",
        "/v1/accounts/acct-a/ach/outgoing/mv-o1/settlements",
        {"instruction_id": "ins-o1x", "evidence_reference": "ev-o1x"},
        key(PAYER, "k-o1x"),
        200,
    ),
    (
        "card authorization",
        "POST",
        "/v1/accounts/acct-a/card-authorizations",
        {
            "instruction_id": "ins-c1",
            "movement_id": "mv-c1",
            "amount_cents": 300,
            "currency": "USD",
            "external_reference": "ext-c1",
            "merchant_reference": "merchant-1",
        },
        key(CARD, "k-c1"),
        201,
    ),
    (
        "card clearing",
        "POST",
        "/v1/accounts/acct-a/card-authorizations/mv-c1/clearings",
        {
            "instruction_id": "ins-c1x",
            "evidence_reference": "ev-c1x",
            "amount_cents": 300,
            "currency": "USD",
        },
        key(CARD, "k-c1x"),
        200,
    ),
    (
        "risk restriction on acct-b",
        "POST",
        "/v1/accounts/acct-b/risk-restrictions",
        {"instruction_id": "ins-r1", "action": "set", "decision_reference": "dec-r1"},
        key(RISK, "k-r1"),
        200,
    ),
    (
        "correction on acct-a",
        "POST",
        "/v1/accounts/acct-a/corrections",
        {
            "instruction_id": "ins-cor1",
            "correction_id": "cor-1",
            "direction": "credit",
            "amount_cents": 10,
            "currency": "USD",
            "decision_reference": "dec-cor1",
        },
        key(CORRECTOR, "k-cor1"),
        201,
    ),
]


def run_steps(client: Any, steps: list[Any], on_done: Any = None) -> None:
    """Run steps in order; each must return its expected status. on_done(index) after each success."""
    for index, (name, method, path, body, headers, want) in enumerate(steps):
        response = client.request(method, path, json=body, headers=headers)
        if response.status_code != want:
            raise AssertionError(
                f"{name}: expected {want}, got {response.status_code}: {response.text[:200]}"
            )
        if on_done is not None:
            on_done(index)


def wait_for_go(index: int) -> None:
    """Report a committed step, then wait for the parent: the kill point is then exact, not a race."""
    print(f"DONE {index}", flush=True)
    sys.stdin.readline()


def worker_main(db: str) -> None:
    """Child process: run the sequence on the entry point, printing one line per committed step."""
    from starlette.testclient import TestClient

    from abm.main import app_from_environment

    os.environ.update(
        ABM_MODE="verification",
        ABM_DB_PATH=db,
        ABM_TRUSTED_INGRESS="true",
        ABM_CLOCK_MODE="system",
    )
    client = TestClient(app_from_environment())
    run_steps(client, STEPS, on_done=wait_for_go)


if __name__ == "__main__":
    worker_main(sys.argv[1])
