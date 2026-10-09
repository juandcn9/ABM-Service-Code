"""Integer USD cents (INV-01, DEC-0002). No floating point, no other currency."""

from __future__ import annotations

from dataclasses import dataclass

from abm.domain.errors import InvalidValue

# schema magnitude bound (contracts/sqlite-schema.sql): 2**53 - 1, exact in every JSON consumer
MAX_CENTS = 9_007_199_254_740_991
CURRENCY = "USD"


def require_usd(value: object) -> str:
    if type(value) is not str or value != CURRENCY:
        raise InvalidValue("currency must be exactly USD")
    return CURRENCY


@dataclass(frozen=True, order=True)
class Money:
    """Signed cents in [-MAX_CENTS, MAX_CENTS]; every arithmetic result is range-checked."""

    cents: int

    def __post_init__(self) -> None:
        # type(...) is int rejects bool, float, str, and int subclasses
        if type(self.cents) is not int or not -MAX_CENTS <= self.cents <= MAX_CENTS:
            raise InvalidValue("cents must be an integer within the supported range")

    @classmethod
    def positive(cls, cents: object) -> Money:
        """A requested amount: integer cents, at least 1."""
        if type(cents) is not int or cents < 1:
            raise InvalidValue("amount must be a positive integer number of cents")
        return cls(cents)

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.cents + other.cents)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.cents - other.cents)

    def __neg__(self) -> Money:
        return Money(-self.cents)

    @property
    def is_negative(self) -> bool:
        return self.cents < 0
