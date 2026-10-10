"""Helpers shared by the incoming and outgoing ACH operations (FR-02, FR-03, FR-04..FR-06)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from abm.domain.errors import InvalidValue
from abm.domain.money import MAX_CENTS
from abm.ports.storage import AccountSnapshot


def fields(body: object, expected: frozenset[str]) -> Mapping[str, object]:
    """Exactly the contract fields; anything else is refused."""
    if type(body) is not dict or set(body) != expected:
        raise InvalidValue("request fields do not match the contract")
    return body


def amount(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_CENTS:
        raise InvalidValue("amount is not a valid cents value")
    return value


def ledger_id(movement_id: str, effect_kind: str) -> str:
    """One stable id per movement effect, within the stored identifier length."""
    return hashlib.sha256(f"{movement_id}\0{effect_kind}".encode()).hexdigest()


def hold_id(movement_id: str) -> str:
    """One stable id per movement hold."""
    return hashlib.sha256(f"{movement_id}\0hold".encode()).hexdigest()


def movement_data(
    movement_id: str,
    movement_type: str,
    state: str,
    account_id: str,
    account: AccountSnapshot,
) -> dict[str, object]:
    available = account.current_balance_cents - account.held_balance_cents
    return {
        "movement_id": movement_id,
        "movement_type": movement_type,
        "state": state,
        "accounts": [
            {
                "account_id": account_id,
                "current_balance_cents": account.current_balance_cents,
                "held_balance_cents": account.held_balance_cents,
                "available_balance_cents": available,
            }
        ],
    }
