"""A set outgoing block still permits resolving movements already accepted (specs/02 section 7; TASK-20 Minor 2)."""

from __future__ import annotations

from abm.application.caller import CallerContext
from abm.application.outgoing_ach import (
    create_outgoing_ach,
    return_outgoing_ach,
    settle_outgoing_ach,
    submit_outgoing_ach,
)
from abm.application.risk import set_risk_restriction
from abm.domain.results import Success
from abm.persistence.sqlite_store import SqliteUnitOfWork
from tests.integration.store_support import clock, fund, open_started, register

PAYER = CallerContext("pay-1", "payment_orchestrator", "corr-p")
RISK = CallerContext("risk-1", "risk_controller", "corr-r")


def test_a_block_permits_settling_and_returning_an_already_accepted_outgoing_movement(
    tmp_path,
):
    conn = open_started(tmp_path / "abm.sqlite3")
    uow, now = SqliteUnitOfWork(conn), clock()
    register(uow, now, "acct-a")
    fund(uow, now, "acct-a", 1000)
    body = {
        "instruction_id": "ins-o",
        "movement_id": "mv-o",
        "amount_cents": 400,
        "currency": "USD",
        "external_reference": "ext-o",
        "destination_reference": "dest-1",
    }
    assert isinstance(
        create_outgoing_ach(uow, now, PAYER, "k-o", "acct-a", body), Success
    )
    assert isinstance(
        submit_outgoing_ach(
            uow,
            now,
            PAYER,
            "k-s",
            "acct-a",
            "mv-o",
            {"instruction_id": "ins-s", "evidence_reference": "ev-s"},
        ),
        Success,
    )
    assert isinstance(
        set_risk_restriction(
            uow,
            now,
            RISK,
            "k-r",
            "acct-a",
            {"instruction_id": "ins-r", "action": "set", "decision_reference": "dec-r"},
        ),
        Success,
    )

    settled = settle_outgoing_ach(
        uow,
        now,
        PAYER,
        "k-set",
        "acct-a",
        "mv-o",
        {"instruction_id": "ins-set", "evidence_reference": "ev-set"},
    )
    assert isinstance(settled, Success)
    back = return_outgoing_ach(
        uow,
        now,
        PAYER,
        "k-back",
        "acct-a",
        "mv-o",
        {
            "instruction_id": "ins-back",
            "evidence_reference": "ev-back",
            "amount_cents": 400,
            "currency": "USD",
        },
    )
    assert isinstance(back, Success)
    assert conn.execute(
        "SELECT restriction FROM accounts WHERE account_id = 'acct-a'"
    ).fetchone() == ("outgoing_blocked",)
