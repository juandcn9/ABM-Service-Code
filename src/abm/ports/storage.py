"""Storage ports the application needs (specs/03-architecture.md sections 4, 5, 7).

Persistence implements these; the application never sees SQL, connections, or driver errors.
Each aggregate's methods are added by the first task that needs them.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from abm.domain.results import Failure


class StorageFailure(Exception):
    """A storage operation failed; carries the safe, already-mapped result."""

    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.error.code)
        self.failure = failure


@dataclass(frozen=True)
class StoredOutcome:
    """The committed result of one idempotent instruction (DATA-05, DEC-0011)."""

    fingerprint: str
    instruction_id: str
    outcome_class: str  # 'success' or 'deterministic_rejection'
    http_status: int
    body: Mapping[
        str, object
    ]  # {"ok": ..., "data" | "error": ...}; response metadata is added later


@dataclass(frozen=True)
class NewAccount:
    account_id: str
    customer_id: str
    eligibility_reference: str


@dataclass(frozen=True)
class TraceEntry:
    """One accepted state transition (DATA-06)."""

    account_id: str | None
    instruction_id: str
    operation: str
    caller_id: str
    caller_role: str
    correlation_id: str
    occurred_at: str
    movement_id: str | None = None
    ledger_entry_id: str | None = None
    evidence_reference: str | None = None
    movement_state: str | None = None
    external_reference: str | None = None


class WriteTransaction(Protocol):
    """Everything a state-changing instruction may do inside its one write transaction."""

    def find_outcome(self, scope: str, key: str) -> StoredOutcome | None: ...

    def save_outcome(
        self, scope: str, key: str, outcome: StoredOutcome, created_at: str
    ) -> None: ...

    def registration_taken(self, account_id: str, customer_id: str) -> bool:
        """True if either identifier already belongs to a retained account."""
        ...

    def create_account(self, account: NewAccount, created_at: str) -> None:
        """Insert the zero-state open account and its retention row (INV-03, DATA-07)."""
        ...

    def append_trace(self, entry: TraceEntry) -> None: ...


class UnitOfWork(Protocol):
    def write(self) -> AbstractContextManager[WriteTransaction]:
        """BEGIN IMMEDIATE ... COMMIT; any exception rolls back everything (INV-06)."""
        ...
