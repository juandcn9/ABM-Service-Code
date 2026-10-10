"""SQLite implementation of the application storage ports. All SQL is fixed text with bound values."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from abm.persistence.database import read_transaction, to_failure, write_transaction
from abm.ports.storage import (
    AccountRecord,
    AccountSnapshot,
    HoldRecord,
    LedgerPost,
    LedgerRow,
    MovementRecord,
    NewAccount,
    NewMovement,
    StorageFailure,
    StoredOutcome,
    TraceEntry,
    TraceRow,
)


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

    def account_snapshot(self, account_id: str) -> AccountSnapshot | None:
        row = self._conn.execute(
            "SELECT status, current_balance_cents, restriction FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            return None
        held = self._conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM holds"
            " WHERE account_id = ? AND state = 'active'",
            (account_id,),
        ).fetchone()[0]
        return AccountSnapshot(row[0], row[1], held, row[2])

    def get_movement(self, movement_id: str) -> MovementRecord | None:
        row = self._conn.execute(
            "SELECT movement_id, account_id, movement_type, state, amount_cents,"
            " external_reference FROM movements WHERE movement_id = ?",
            (movement_id,),
        ).fetchone()
        return None if row is None else MovementRecord(*row)

    def create_movement(self, movement: NewMovement, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO movements (movement_id, account_id, counterparty_account_id,"
            " movement_type, state, amount_cents, currency, external_reference,"
            " destination_reference, merchant_reference, decision_reference, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?, ?)",
            (
                movement.movement_id,
                movement.account_id,
                movement.counterparty_account_id,
                movement.movement_type,
                movement.state,
                movement.amount_cents,
                movement.external_reference,
                movement.destination_reference,
                movement.merchant_reference,
                movement.decision_reference,
                created_at,
                created_at,
            ),
        )

    def decision_reference_taken(self, decision_reference: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM movements WHERE decision_reference = ? AND movement_type = 'correction'",
            (decision_reference,),
        ).fetchone()
        return row is not None

    def ledger_entry_account(self, entry_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT account_id FROM ledger_entries WHERE entry_id = ?", (entry_id,)
        ).fetchone()
        return None if row is None else row[0]

    def set_movement_state(self, movement_id: str, state: str, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE movements SET state = ?, updated_at = ? WHERE movement_id = ?",
            (state, updated_at, movement_id),
        )

    def evidence_reference_taken(self, evidence_reference: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM movement_evidence WHERE evidence_reference = ?",
            (evidence_reference,),
        ).fetchone()
        return row is not None

    def add_evidence(
        self, evidence_reference: str, movement_id: str, kind: str, occurred_at: str
    ) -> None:
        self._conn.execute(
            "INSERT INTO movement_evidence (evidence_reference, movement_id, evidence_kind,"
            " occurred_at) VALUES (?, ?, ?, ?)",
            (evidence_reference, movement_id, kind, occurred_at),
        )

    def post_ledger(self, post: LedgerPost, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO ledger_entries (entry_id, account_id, movement_id, effect_kind,"
            " direction, amount_cents, authorized_caller_id, authorized_role,"
            " external_reference, correction_of_entry_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                post.entry_id,
                post.account_id,
                post.movement_id,
                post.effect_kind,
                post.direction,
                post.amount_cents,
                post.caller_id,
                post.caller_role,
                post.external_reference,
                post.correction_of_entry_id,
                created_at,
            ),
        )

    def ledger_amount(self, movement_id: str, effect_kind: str) -> int | None:
        row = self._conn.execute(
            "SELECT amount_cents FROM ledger_entries WHERE movement_id = ? AND effect_kind = ?",
            (movement_id, effect_kind),
        ).fetchone()
        return None if row is None else row[0]

    def apply_balance(self, account_id: str, delta_cents: int) -> None:
        self._conn.execute(
            "UPDATE accounts SET current_balance_cents = current_balance_cents + ?"
            " WHERE account_id = ?",
            (delta_cents, account_id),
        )

    def set_restriction(
        self, account_id: str, restriction: str, decision_reference: str | None
    ) -> None:
        # the schema requires the decision reference exactly when a block is set
        self._conn.execute(
            "UPDATE accounts SET restriction = ?, restriction_decision_reference = ?"
            " WHERE account_id = ?",
            (restriction, decision_reference, account_id),
        )

    def hold_state(self, movement_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT state FROM holds WHERE movement_id = ?", (movement_id,)
        ).fetchone()
        return None if row is None else row[0]

    def create_hold(
        self,
        hold_id: str,
        movement_id: str,
        account_id: str,
        amount_cents: int,
        created_at: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO holds (hold_id, movement_id, account_id, amount_cents, state, created_at)"
            " VALUES (?, ?, ?, ?, 'active', ?)",
            (hold_id, movement_id, account_id, amount_cents, created_at),
        )

    def finalize_hold(
        self,
        movement_id: str,
        state: str,
        evidence_reference: str | None,
        finalized_at: str,
    ) -> None:
        cursor = self._conn.execute(
            "UPDATE holds SET state = ?, evidence_reference = ?, finalized_at = ?"
            " WHERE movement_id = ? AND state = 'active'",
            (state, evidence_reference, finalized_at, movement_id),
        )
        if cursor.rowcount != 1:
            # no single active hold: never finalize silently; the write rolls back as INTERNAL_ERROR
            raise sqlite3.IntegrityError("no single active hold to finalize")


class SqliteReadTransaction:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_account(self, account_id: str) -> AccountRecord | None:
        row = self._conn.execute(
            "SELECT account_id, status, restriction, current_balance_cents"
            " FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            return None
        holds = tuple(
            HoldRecord(*hold)
            for hold in self._conn.execute(
                "SELECT hold_id, movement_id, amount_cents, state FROM holds"
                " WHERE account_id = ? AND state = 'active' ORDER BY created_at, hold_id",
                (account_id,),
            )
        )
        return AccountRecord(row[0], row[1], row[2], row[3], holds)

    def history_page(
        self, account_id: str, after_sequence: int, limit: int
    ) -> list[LedgerRow]:
        return [
            LedgerRow(*row)
            for row in self._conn.execute(
                "SELECT sequence, entry_id, movement_id, effect_kind, direction,"
                " amount_cents, created_at FROM ledger_entries"
                " WHERE account_id = ? AND sequence > ? ORDER BY sequence ASC LIMIT ?",
                (account_id, after_sequence, limit),
            )
        ]

    def trace_cutoff(self) -> int:
        row = self._conn.execute("SELECT MAX(sequence) FROM audit_trace").fetchone()
        return int(row[0] or 0)

    def trace_page(
        self, after_sequence: int, cutoff_sequence: int, limit: int
    ) -> list[TraceRow]:
        return [
            TraceRow(*row)
            for row in self._conn.execute(
                "SELECT t.sequence, t.account_id, t.instruction_id, t.movement_id, t.operation,"
                " t.caller_id, t.caller_role, t.correlation_id, t.occurred_at,"
                " t.ledger_entry_id, t.movement_state, l.effect_kind, l.direction,"
                " l.amount_cents, t.evidence_reference, t.external_reference"
                " FROM audit_trace t LEFT JOIN ledger_entries l ON l.entry_id = t.ledger_entry_id"
                " WHERE t.sequence > ? AND t.sequence <= ? ORDER BY t.sequence ASC LIMIT ?",
                (after_sequence, cutoff_sequence, limit),
            )
        ]


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

    @contextmanager
    def read(self) -> Iterator[SqliteReadTransaction]:
        try:
            with read_transaction(self._conn):
                yield SqliteReadTransaction(self._conn)
        except sqlite3.Error as exc:
            raise StorageFailure(to_failure(exc)) from exc
