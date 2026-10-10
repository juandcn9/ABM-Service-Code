"""A non-storable failure returned after a write leaves nothing committed (TEST-16, INV-06)."""

from __future__ import annotations

import pathlib

from abm.application.caller import CallerContext
from abm.application.idempotency import Response, run_idempotent, scope_key
from abm.domain.fingerprint import fingerprint
from abm.domain.results import Result, failure
from abm.persistence.sqlite_store import SqliteUnitOfWork
from abm.ports.storage import NewAccount, WriteTransaction
from tests.integration.store_support import clock, open_started

REGISTRAR = CallerContext("registrar-1", "account_registrar", "corr-1")


def test_a_busy_failure_after_a_write_commits_nothing(tmp_path: pathlib.Path):
    conn = open_started(tmp_path / "abm.sqlite3")
    uow, now = SqliteUnitOfWork(conn), clock()

    def work(tx: WriteTransaction, at: str) -> Result[Response]:
        tx.create_account(NewAccount("acct-x", "cust-x", "elig-1"), at)
        return failure("SERVICE_BUSY", "Retry.", retryable=True)

    result = run_idempotent(
        uow,
        now,
        scope=scope_key("acct-x", "probe"),
        key="k-busy",
        fingerprint=fingerprint("probe", {"account_id": "acct-x"}),
        instruction_id="ins-busy",
        work=work,
    )

    assert not result.ok and result.error.code == "SERVICE_BUSY"
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone() == (0,)
    assert conn.execute("SELECT COUNT(*) FROM idempotency_outcomes").fetchone() == (0,)
