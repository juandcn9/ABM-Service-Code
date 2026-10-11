"""TASK-37 worker: one process that drives the entry point against a shared database file.

Usage: multiprocess_worker.py DB ACTION [AMOUNT]
  ACTION transfer  moves AMOUNT cents from acct-a to acct-b (movement id from the PID).
  ACTION credit    posts an incoming settlement of AMOUNT cents to acct-a.
The worker prints READY, waits for one line on stdin (the parent's go signal), runs the action, and
prints RESULT <http status> <error code or OK>. Standard streams are the only channel; no timing is used.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)


def main(db: str, action: str, amount: int) -> None:
    from starlette.testclient import TestClient

    from abm.main import app_from_environment
    from tests.integration.continuity_sequence import PAYER

    os.environ.update(
        ABM_MODE="verification",
        ABM_DB_PATH=db,
        ABM_TRUSTED_INGRESS="true",
        ABM_CLOCK_MODE="system",
    )
    client = TestClient(app_from_environment())
    tag = f"p{os.getpid()}"
    print("READY", flush=True)
    sys.stdin.readline()  # the parent's go signal
    if action == "transfer":
        response = client.post(
            "/v1/transfers/internal",
            json={
                "instruction_id": f"ins-{tag}",
                "movement_id": f"mv-{tag}",
                "source_account_id": "acct-a",
                "destination_account_id": "acct-b",
                "amount_cents": amount,
                "currency": "USD",
            },
            headers={**PAYER, "Idempotency-Key": f"k-{tag}"},
        )
    else:
        notice = client.post(
            "/v1/accounts/acct-a/ach/incoming",
            json={
                "instruction_id": f"ins-{tag}",
                "movement_id": f"mv-{tag}",
                "amount_cents": amount,
                "currency": "USD",
                "external_reference": f"ext-{tag}",
            },
            headers={**PAYER, "Idempotency-Key": f"k-{tag}"},
        )
        response = (
            client.post(
                f"/v1/accounts/acct-a/ach/incoming/mv-{tag}/settlements",
                json={
                    "instruction_id": f"ins-s-{tag}",
                    "evidence_reference": f"ev-{tag}",
                },
                headers={**PAYER, "Idempotency-Key": f"k-s-{tag}"},
            )
            if notice.status_code == 201
            else notice
        )
    code = (
        "OK"
        if response.status_code < 300
        else response.json().get("error", {}).get("code", "?")
    )
    print(f"RESULT {response.status_code} {code}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
