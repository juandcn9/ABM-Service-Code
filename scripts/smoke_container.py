"""TASK-36 black-box smoke check of the running container image (DEC-0067, DEC-0069).

Usage (repository root, on a host with a container engine):  python scripts/smoke_container.py

Builds the image and starts it with a fresh volume, then runs the probes over HTTP:
  liveness and readiness; registration; an authorized account read; one incoming ACH credit
  (notice then settlement) visible in history and balance; and one denied request with no state
  change. Standard library only. The probe sequence is in run_smoke(), which takes a call adapter,
  so the same steps run over HTTP here and in-process in tests.
"""

from __future__ import annotations

import json
import pathlib
import secrets
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from check_container import (  # type: ignore[import-not-found]
    PORT,
    CheckFailed,
    host_port,
    run,
    wait_for,
)

Call = Callable[[str, str, Any, dict[str, str]], tuple[int, dict[str, Any]]]
ACCOUNT = "acct-smoke"
AMOUNT = 100


def caller(role: str, who: str, scope: str | None = None) -> dict[str, str]:
    headers = {
        "X-Caller-Id": who,
        "X-Caller-Role": role,
        "X-Correlation-Id": f"smoke-{who}",
    }
    if scope is not None:
        headers["X-Account-Scope"] = scope
    return headers


def run_smoke(call: Call) -> list[str]:
    """The probe sequence. Returns the failures by name; an empty list means the smoke check passed."""
    failures: list[str] = []

    def expect(label: str, status: int, body: dict[str, Any], want: int) -> bool:
        if status != want:
            failures.append(f"{label}: expected HTTP {want}, got {status}")
            return False
        return True

    def balance(who: str) -> tuple[int, Any]:
        status, body = call(
            "GET",
            f"/v1/accounts/{ACCOUNT}",
            None,
            caller("account_reader", who, ACCOUNT),
        )
        return status, body.get("data", {}).get("balances", {}).get(
            "current_balance_cents"
        )

    status, _ = call("GET", "/health/live", None, {})
    expect("liveness", status, {}, 200)
    status, _ = call("GET", "/health/ready", None, {})
    expect("readiness", status, {}, 200)

    registration = {
        "instruction_id": "smoke-reg-1",
        "account_id": ACCOUNT,
        "customer_id": "cust-smoke",
        "currency": "USD",
        "eligibility_reference": "elig-smoke",
    }
    status, body = call(
        "POST",
        "/v1/accounts/registrations",
        registration,
        {**caller("account_registrar", "smoke-reg"), "Idempotency-Key": "smoke-k-reg"},
    )
    expect("registration", status, body, 201)

    status, body = call(
        "GET",
        f"/v1/accounts/{ACCOUNT}",
        None,
        caller("account_reader", "smoke-rd", ACCOUNT),
    )
    if (
        expect("authorized account read", status, body, 200)
        and body.get("data", {}).get("account_id") != ACCOUNT
    ):
        failures.append(
            "authorized account read: the account returned is not the one registered"
        )

    notice = {
        "instruction_id": "smoke-ins-1",
        "movement_id": "smoke-mv-1",
        "amount_cents": AMOUNT,
        "currency": "USD",
        "external_reference": "smoke-ext-1",
    }
    status, body = call(
        "POST",
        f"/v1/accounts/{ACCOUNT}/ach/incoming",
        notice,
        {
            **caller("payment_orchestrator", "smoke-pay"),
            "Idempotency-Key": "smoke-k-notice",
        },
    )
    expect("incoming ACH notice", status, body, 201)
    settlement = {"instruction_id": "smoke-set-1", "evidence_reference": "smoke-ev-1"}
    status, body = call(
        "POST",
        f"/v1/accounts/{ACCOUNT}/ach/incoming/smoke-mv-1/settlements",
        settlement,
        {
            **caller("payment_orchestrator", "smoke-pay"),
            "Idempotency-Key": "smoke-k-settle",
        },
    )
    expect("incoming ACH settlement", status, body, 200)

    status, body = call(
        "GET",
        f"/v1/accounts/{ACCOUNT}/transactions",
        None,
        caller("account_reader", "smoke-rd", ACCOUNT),
    )
    if expect("history read", status, body, 200):
        credits = [
            i
            for i in body.get("data", {}).get("items", [])
            if i.get("amount_cents") == AMOUNT
        ]
        if len(credits) != 1:
            failures.append(
                f"history: expected one credit of {AMOUNT} cents, found {len(credits)}"
            )

    status, balance_before = balance("smoke-rd")
    if status != 200 or balance_before != AMOUNT:
        failures.append(
            f"balance after settlement: expected {AMOUNT} cents, got {balance_before}"
        )

    status, body = call("GET", f"/v1/accounts/{ACCOUNT}", None, {})
    if (
        expect("denied read without caller context", status, body, 401)
        and body.get("error", {}).get("code") != "UNAUTHORIZED"
    ):
        failures.append("denied read: the error code is not UNAUTHORIZED")
    status, body = call(
        "POST",
        "/v1/accounts/registrations",
        {**registration, "instruction_id": "smoke-reg-2", "account_id": "acct-denied"},
        {
            **caller("payment_orchestrator", "smoke-pay"),
            "Idempotency-Key": "smoke-k-denied",
        },
    )
    expect("denied registration by a payment role", status, body, 403)

    status, after = balance("smoke-rd")
    if status != 200 or after != balance_before:
        failures.append("denied requests changed the balance")
    status, body = call(
        "GET",
        "/v1/accounts/acct-denied",
        None,
        caller("account_reader", "smoke-rd", "acct-denied"),
    )
    if status != 404:
        failures.append(
            f"denied registration left an account behind (read gave {status})"
        )
    return failures


def http_call(base: str) -> Call:
    def call(
        method: str, path: str, body: Any, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", **headers},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, _json(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _json(exc.read())

    return call


def _json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw or b"{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def main(argv: list[str]) -> int:
    tag = secrets.token_hex(4)
    image, volume, name = (
        f"abm-smoke:{tag}",
        f"abm-smoke-data-{tag}",
        f"abm-smoke-{tag}",
    )
    try:
        run("docker", "build", "-t", image, ".")
        run("docker", "volume", "create", volume)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--read-only",
            "-v",
            f"{volume}:/data",
            "-e",
            "ABM_MODE=demonstration",
            "-e",
            "ABM_TRUSTED_INGRESS=true",
            "-e",
            "ABM_CLOCK_MODE=system",
            "-p",
            f"127.0.0.1::{PORT}",
            image,
        )
        base = f"http://127.0.0.1:{host_port('docker', name)}"
        wait_for(f"{base}/health/ready", 200)
        failures = run_smoke(http_call(base))
        if failures:
            raise CheckFailed("; ".join(failures))
        print(
            "SMOKE CHECK PASSED: liveness, readiness, registration, authorized read, credit in history and balance, denied requests with no state change"
        )
        return 0
    except CheckFailed as exc:
        print(f"SMOKE CHECK FAILED: {exc}")
        return 1
    finally:
        run("docker", "rm", "-f", name, check=False)
        run("docker", "volume", "rm", volume, check=False)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
