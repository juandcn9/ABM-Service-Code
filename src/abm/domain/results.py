"""Typed application results: expected failures are values, not exceptions (specs/03-architecture.md section 6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from abm.domain.errors import InvalidValue

# stable codes from specs/04-api.md section 2
ERROR_CODES = frozenset(
    {
        "VALIDATION_ERROR",
        "UNAUTHORIZED",
        "FORBIDDEN_SCOPE",
        "ACCOUNT_NOT_FOUND",
        "MOVEMENT_NOT_FOUND",
        "ACCOUNT_CLOSED",
        "DUPLICATE_ACCOUNT",
        "IDEMPOTENCY_CONFLICT",
        "INVALID_TRANSITION",
        "AMOUNT_MISMATCH",
        "CLOSURE_PRECONDITION_FAILED",
        "INSUFFICIENT_FUNDS",
        "OUTGOING_BLOCKED",
        "UNSUPPORTED_OPERATION",
        "SERVICE_BUSY",
        "SERVICE_UNREADY",
        "INTERNAL_ERROR",
    }
)


@dataclass(frozen=True)
class Error:
    code: str
    safe_message: str
    retryable: bool

    def __post_init__(self) -> None:
        if self.code not in ERROR_CODES or not self.safe_message:
            raise InvalidValue("error needs a stable code and a safe message")


@dataclass(frozen=True)
class Success[T]:
    value: T
    replayed: bool = False
    ok: ClassVar[bool] = True


@dataclass(frozen=True)
class Failure:
    error: Error
    ok: ClassVar[bool] = False


type Result[T] = Success[T] | Failure


def failure(code: str, safe_message: str, retryable: bool = False) -> Failure:
    return Failure(Error(code, safe_message, retryable))
