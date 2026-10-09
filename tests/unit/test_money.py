"""Integer-cent money (INV-01, TEST-24 integer-overflow part)."""

from __future__ import annotations

import pytest

from abm.domain.errors import InvalidValue
from abm.domain.money import CURRENCY, MAX_CENTS, Money, require_usd


def test_amounts_are_positive_integers_only() -> None:
    assert Money.positive(1).cents == 1
    assert Money.positive(MAX_CENTS).cents == MAX_CENTS
    for bad in (0, -1, MAX_CENTS + 1, 1.0, 10.5, "100", None, True, False, [1], 2**63):
        with pytest.raises(InvalidValue):
            Money.positive(bad)


def test_signed_balances_stay_in_range_and_integer() -> None:
    assert Money(-MAX_CENTS).is_negative
    assert not Money(0).is_negative
    for bad in (MAX_CENTS + 1, -MAX_CENTS - 1, 1.5, True, "1"):
        with pytest.raises(InvalidValue):
            Money(bad)  # type: ignore[arg-type]


def test_arithmetic_is_exact_and_range_checked() -> None:
    assert (Money(100) - Money(250)).cents == -150
    assert (Money(100) + Money(250)).cents == 350
    assert (-Money(7)).cents == -7
    assert Money(1) < Money(2)
    # cents never go through float: a sum past 2**53 would silently lose precision there
    with pytest.raises(InvalidValue):
        Money(MAX_CENTS) + Money(1)
    with pytest.raises(InvalidValue):
        Money(-MAX_CENTS) - Money(1)


def test_money_is_immutable_and_hashable() -> None:
    money = Money(5)
    with pytest.raises(AttributeError):
        money.cents = 6  # type: ignore[misc]
    assert {Money(5), Money(5)} == {money}


def test_currency_is_exactly_usd() -> None:
    assert require_usd("USD") == CURRENCY == "USD"
    for bad in ("usd", "EUR", "USD ", "", None, 840, b"USD"):
        with pytest.raises(InvalidValue):
            require_usd(bad)


def test_the_bound_is_the_schema_literal() -> None:
    # contracts/sqlite-schema.sql CHECK ranges use exactly 2**53 - 1
    assert MAX_CENTS == 9_007_199_254_740_991 == 2**53 - 1


def test_arithmetic_with_a_non_money_operand_is_a_type_error() -> None:
    for other in (1, True, 1.5, "1", None):
        with pytest.raises(TypeError):
            Money(1) + other  # type: ignore[operator]
        with pytest.raises(TypeError):
            Money(1) - other  # type: ignore[operator]
