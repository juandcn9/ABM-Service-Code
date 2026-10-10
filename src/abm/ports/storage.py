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


@dataclass(frozen=True)
class AccountSnapshot:
    """An account's status and balances inside one write transaction."""

    status: str
    current_balance_cents: int
    held_balance_cents: int
    restriction: str = "none"


@dataclass(frozen=True)
class MovementRecord:
    movement_id: str
    account_id: str
    movement_type: str
    state: str
    amount_cents: int
    external_reference: str | None


@dataclass(frozen=True)
class NewMovement:
    movement_id: str
    account_id: str
    movement_type: str
    state: str
    amount_cents: int
    external_reference: str | None
    destination_reference: str | None = None
    counterparty_account_id: str | None = None
    merchant_reference: str | None = None
    decision_reference: str | None = None


@dataclass(frozen=True)
class LedgerPost:
    """One append-only ledger effect (DATA-02, INV-07)."""

    entry_id: str
    account_id: str
    movement_id: str
    effect_kind: str
    direction: str
    amount_cents: int
    caller_id: str
    caller_role: str
    external_reference: str | None
    correction_of_entry_id: str | None = None


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

    def account_snapshot(self, account_id: str) -> AccountSnapshot | None: ...

    def get_movement(self, movement_id: str) -> MovementRecord | None: ...

    def create_movement(self, movement: NewMovement, created_at: str) -> None: ...

    def decision_reference_taken(self, decision_reference: str) -> bool:
        """True if a correction already uses this decision (one correction per decision)."""
        ...

    def ledger_entry_account(self, entry_id: str) -> str | None:
        """The account of one ledger entry, or None if no such entry exists."""
        ...

    def set_movement_state(
        self, movement_id: str, state: str, updated_at: str
    ) -> None: ...

    def evidence_reference_taken(self, evidence_reference: str) -> bool: ...

    def add_evidence(
        self, evidence_reference: str, movement_id: str, kind: str, occurred_at: str
    ) -> None: ...

    def post_ledger(self, post: LedgerPost, created_at: str) -> None: ...

    def apply_balance(self, account_id: str, delta_cents: int) -> None: ...

    def set_restriction(
        self, account_id: str, restriction: str, decision_reference: str | None
    ) -> None:
        """Set or clear the outgoing block with its decision reference (INV-11, specs/02 section 7)."""
        ...

    def ledger_amount(self, movement_id: str, effect_kind: str) -> int | None:
        """The amount of one ledger effect of a movement, or None if it has not been posted."""
        ...

    def hold_state(self, movement_id: str) -> str | None:
        """The state of the movement's hold, or None if it has none (one hold per movement)."""
        ...

    def create_hold(
        self,
        hold_id: str,
        movement_id: str,
        account_id: str,
        amount_cents: int,
        created_at: str,
    ) -> None: ...

    def finalize_hold(
        self,
        movement_id: str,
        state: str,
        evidence_reference: str | None,
        finalized_at: str,
    ) -> None: ...


@dataclass(frozen=True)
class HoldRecord:
    hold_id: str
    movement_id: str
    amount_cents: int
    state: str


@dataclass(frozen=True)
class AccountRecord:
    """Stored facts of one account; available balance is derived from them, never stored."""

    account_id: str
    status: str
    restriction: str
    current_balance_cents: int
    active_holds: tuple[HoldRecord, ...]


@dataclass(frozen=True)
class LedgerRow:
    sequence: int
    entry_id: str
    movement_id: str
    effect_kind: str
    direction: str
    amount_cents: int
    created_at: str


@dataclass(frozen=True)
class TraceRow:
    """One accepted trace record joined only to immutable ledger data (specs/05 section 6)."""

    sequence: int
    account_id: str | None
    instruction_id: str
    movement_id: str | None
    operation: str
    caller_id: str
    caller_role: str
    correlation_id: str
    occurred_at: str
    ledger_entry_id: str | None
    movement_state: str | None
    effect_kind: str | None
    direction: str | None
    amount_cents: int | None
    evidence_reference: str | None
    external_reference: str | None


class ReadTransaction(Protocol):
    """Reads inside one consistent snapshot; nothing here can write."""

    def get_account(self, account_id: str) -> AccountRecord | None: ...

    def history_page(
        self, account_id: str, after_sequence: int, limit: int
    ) -> list[LedgerRow]:
        """Ledger entries with sequence > after_sequence, ascending, at most limit rows."""
        ...

    def trace_cutoff(self) -> int:
        """The highest committed audit sequence, or 0 when there is none."""
        ...

    def trace_page(
        self, after_sequence: int, cutoff_sequence: int, limit: int
    ) -> list[TraceRow]:
        """Records with after_sequence < sequence <= cutoff_sequence, ascending."""
        ...


class UnitOfWork(Protocol):
    def write(self) -> AbstractContextManager[WriteTransaction]:
        """BEGIN IMMEDIATE ... COMMIT; any exception rolls back everything (INV-06)."""
        ...

    def read(self) -> AbstractContextManager[ReadTransaction]:
        """One consistent read snapshot; everything read inside shares the same committed state."""
        ...
