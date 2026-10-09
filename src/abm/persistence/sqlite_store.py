"""SQLite implementation of the application storage ports. All SQL is fixed text with bound values."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from abm.persistence.database import to_failure, write_transaction
from abm.ports.storage import NewAccount, StorageFailure, StoredOutcome, TraceEntry


class SqliteWriteTransaction:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_outcome(self, scope: str, key: str) -> StoredOutcome | None:
        row = self._conn.execute(
            "SELECT fingerprint, instruction_id, outcome_class, http_status, response_json"
            " FROM idempotency_outcomes WHERE scope = ? AND idempotency_key = ?",
            (scope, key),
        ).fetchone()
        if row is None:
            return None
        return StoredOutcome(row[0], row[1], row[2], row[3], json.loads(row[4]))

    def save_outcome(
        self, scope: str, key: str, outcome: StoredOutcome, created_at: str
    ) -> None:
        self._conn.execute(
            "INSERT INTO idempotency_outcomes (scope, idempotency_key, fingerprint,"
            " instruction_id, outcome_class, http_status, response_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scope,
                key,
                outcome.fingerprint,
                outcome.instruction_id,
                outcome.outcome_class,
                outcome.http_status,
                json.dumps(outcome.body, sort_keys=True, separators=(",", ":")),
                created_at,
            ),
        )

    def registration_taken(self, account_id: str, customer_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM accounts WHERE account_id = ? OR customer_id = ? LIMIT 1",
            (account_id, customer_id),
        ).fetchone()
        return row is not None

    def create_account(self, account: NewAccount, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO accounts (account_id, customer_id, currency, eligibility_reference,"
            " status, created_at) VALUES (?, ?, 'USD', ?, 'open', ?)",
            (
                account.account_id,
                account.customer_id,
                account.eligibility_reference,
                created_at,
            ),
        )
        self._conn.execute(
            "INSERT INTO retention_metadata (account_id, record_type, record_id)"
            " VALUES (?, 'account', ?)",
            (account.account_id, account.account_id),
        )

    def append_trace(self, entry: TraceEntry) -> None:
        self._conn.execute(
            "INSERT INTO audit_trace (account_id, instruction_id, movement_id,"
            " ledger_entry_id, evidence_reference, movement_state, operation, outcome,"
            " caller_id, caller_role, correlation_id, external_reference, occurred_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?, ?, ?)",
            (
                entry.account_id,
                entry.instruction_id,
                entry.movement_id,
                entry.ledger_entry_id,
                entry.evidence_reference,
                entry.movement_state,
                entry.operation,
                entry.caller_id,
                entry.caller_role,
                entry.correlation_id,
                entry.external_reference,
                entry.occurred_at,
            ),
        )


class SqliteUnitOfWork:
    """One write transaction per instruction; driver errors become safe StorageFailure values."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @contextmanager
    def write(self) -> Iterator[SqliteWriteTransaction]:
        try:
            with write_transaction(self._conn):
                yield SqliteWriteTransaction(self._conn)
        except sqlite3.Error as exc:
            raise StorageFailure(to_failure(exc)) from exc
