"""Transactional idempotency for every state-changing instruction (INV-17, DEC-0011, specs/02 section 3).

Inside one serialized write transaction: find the stored outcome for the scope and key; replay it
exactly when the fingerprint matches; report a conflict without any write when it does not;
otherwise run the instruction and store either its committed success or its deterministic
rejection. Any other failure rolls everything back and stores nothing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from abm.domain.identifiers import format_instant
from abm.domain.results import Error, Failure, Result, Success, failure
from abm.ports.clock import Clock
from abm.ports.storage import (
    StorageFailure,
    StoredOutcome,
    UnitOfWork,
    WriteTransaction,
)

# DEC-0011: the only failures stored as a deterministic outcome, with their HTTP status.
# Exactly the set the idempotency_outcomes CHECK constraint allows.
STORABLE_REJECTIONS: Mapping[str, int] = {
    "ACCOUNT_NOT_FOUND": 404,
    "MOVEMENT_NOT_FOUND": 404,
    "DUPLICATE_ACCOUNT": 409,
    "INVALID_TRANSITION": 409,
    "ACCOUNT_CLOSED": 422,
    "AMOUNT_MISMATCH": 422,
    "CLOSURE_PRECONDITION_FAILED": 422,
    "INSUFFICIENT_FUNDS": 422,
    "OUTGOING_BLOCKED": 422,
}


@dataclass(frozen=True)
class Response:
    """A committed success: HTTP status and the data object. Metadata is added at the edge."""

    status: int
    data: Mapping[str, object]


class _Abort(Exception):
    """Roll the transaction back and return this result unchanged."""

    def __init__(self, result: Failure) -> None:
        super().__init__(result.error.code)
        self.result = result


def scope_key(subject_id: str, operation: str) -> str:
    """The stored scope for (subject, operation).

    specs/02 defines the scope as customer_id + registration or account_id + operation, but the
    schema limits the stored value to 128 characters of [-A-Za-z0-9._~], which two 128-character
    identifiers cannot fit. A SHA-256 hex digest of the pair is deterministic, unambiguous, and
    within the alphabet.
    """
    return hashlib.sha256(f"{subject_id}\0{operation}".encode()).hexdigest()


def _error_body(error: Error) -> dict[str, object]:
    return {
        "code": error.code,
        "message": error.safe_message,
        "retryable": error.retryable,
    }


def _to_outcome(
    result: Result[Response], fingerprint: str, instruction_id: str
) -> StoredOutcome | None:
    if isinstance(result, Success):
        body: dict[str, object] = {"ok": True, "data": dict(result.value.data)}
        return StoredOutcome(
            fingerprint, instruction_id, "success", result.value.status, body
        )
    status = STORABLE_REJECTIONS.get(result.error.code)
    if status is None:
        return None
    body = {"ok": False, "error": _error_body(result.error)}
    return StoredOutcome(
        fingerprint, instruction_id, "deterministic_rejection", status, body
    )


def _replay(stored: StoredOutcome) -> Result[Response]:
    body = stored.body
    try:
        if body["ok"] is True:
            data = body["data"]
            assert isinstance(data, Mapping)
            return Success(Response(stored.http_status, data), replayed=True)
        raw = body["error"]
        assert isinstance(raw, Mapping)
        error = Error(str(raw["code"]), str(raw["message"]), bool(raw["retryable"]))
        return Failure(error, replayed=True)
    except (KeyError, AssertionError):
        return failure("INTERNAL_ERROR", "An unexpected error occurred.")


def run_idempotent(
    uow: UnitOfWork,
    clock: Clock,
    *,
    scope: str,
    key: str,
    fingerprint: str,
    instruction_id: str,
    work: Callable[[WriteTransaction, str], Result[Response]],
) -> Result[Response]:
    """Run work(tx, now) exactly once per (scope, key, fingerprint).

    work must return a Failure only before it has written anything, and every Failure it returns
    is either a storable rejection or a transient failure; transient ones are rolled back.
    """
    try:
        now = format_instant(clock.now())
    # an unavailable clock rejects time-dependent work; there is no wall-clock fallback
    except Exception:  # noqa: BLE001
        return failure("SERVICE_UNREADY", "The service is not ready.")
    try:
        with uow.write() as tx:
            stored = tx.find_outcome(scope, key)
            if stored is not None:
                if stored.fingerprint != fingerprint:
                    return failure(
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was already used for a different request.",
                    )
                return _replay(stored)
            result = work(tx, now)
            outcome = _to_outcome(result, fingerprint, instruction_id)
            if outcome is None:
                assert isinstance(result, Failure)  # a Success always has an outcome
                raise _Abort(result)
            tx.save_outcome(scope, key, outcome, now)
            return result
    except _Abort as aborted:
        return aborted.result
    except StorageFailure as exc:
        return exc.failure
