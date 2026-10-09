"""Typed results, fingerprints, and the controllable clock (INV-12, INV-17, DEC-0011)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from abm.domain.errors import InvalidValue
from abm.domain.fingerprint import fingerprint
from abm.domain.results import ERROR_CODES, Error, Failure, Success, failure
from harness.clock import ControllableClock


def test_success_and_failure_are_discriminated_values() -> None:
    ok = Success({"balance": 5})
    assert ok.ok is True and ok.replayed is False and ok.value == {"balance": 5}
    assert Success(1, replayed=True).replayed is True
    bad = failure("INSUFFICIENT_FUNDS", "Available funds are insufficient.")
    assert isinstance(bad, Failure) and bad.ok is False
    assert bad.error == Error(
        "INSUFFICIENT_FUNDS", "Available funds are insufficient.", False
    )
    assert failure("SERVICE_BUSY", "Try again.", retryable=True).error.retryable is True


def test_errors_need_a_stable_code_and_message() -> None:
    assert "IDEMPOTENCY_CONFLICT" in ERROR_CODES and len(ERROR_CODES) == 17
    for code, message in (("NOT_A_CODE", "x"), ("", "x"), ("INTERNAL_ERROR", "")):
        with pytest.raises(InvalidValue):
            Error(code, message, False)


def test_fingerprint_is_deterministic_and_order_independent() -> None:
    a = fingerprint(
        "incoming_ach_settlement",
        {"account_id": "a1", "amount_cents": 500, "currency": "USD"},
    )
    b = fingerprint(
        "incoming_ach_settlement",
        {"currency": "USD", "amount_cents": 500, "account_id": "a1"},
    )
    assert a == b
    assert len(a) == 64 and set(a) <= set("0123456789abcdef")


def test_fingerprint_changes_with_every_input() -> None:
    base: dict[str, str | int | None] = {
        "account_id": "a1",
        "amount_cents": 500,
        "currency": "USD",
    }
    original = fingerprint("op", base)
    variants = [
        fingerprint("other_op", base),
        fingerprint("op", {**base, "account_id": "a2"}),
        fingerprint("op", {**base, "amount_cents": 501}),
        fingerprint("op", {**base, "currency": "usd"}),
        fingerprint("op", {**base, "extra": "x"}),
        fingerprint("op", {k: v for k, v in base.items() if k != "currency"}),
    ]
    assert len({original, *variants}) == 7


def test_fingerprint_does_not_confuse_types_or_null_with_absent() -> None:
    assert fingerprint("op", {"v": 5}) != fingerprint("op", {"v": "5"})
    assert fingerprint("op", {"v": None}) != fingerprint("op", {})
    assert fingerprint("op", {"v": "a,b"}) != fingerprint("op", {"v": "a", "w": "b"})
    # separator characters inside values cannot collide with structure
    assert fingerprint("op", {"a": "1", "b": "2"}) != fingerprint(
        "op", {"a": '1","b":"2'}
    )


def test_fingerprint_rejects_values_without_one_canonical_form() -> None:
    for value in (1.5, True, [1], {"k": 1}, b"x", float("nan")):
        with pytest.raises(InvalidValue):
            fingerprint("op", {"v": value})  # type: ignore[dict-item]
    with pytest.raises(InvalidValue):
        fingerprint("bad op", {})


def test_fingerprint_known_vector_is_stable() -> None:
    # pins the canonical encoding so a later refactor cannot silently change stored fingerprints;
    # the value is sha256 of {"fields":{"currency":"USD","customer_id":"c1"},"operation":"register"} computed with sha256sum
    assert (
        fingerprint("register", {"customer_id": "c1", "currency": "USD"})
        == "80dd3e79b2d7aecf2a7a3922f229fb449b43a0ba634a315739ffad34f58941ce"
    )


def test_clock_moves_only_when_told_to() -> None:
    start = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    clock = ControllableClock(start)
    assert clock.now() == clock.now() == start  # reading never advances time
    clock.advance(90)
    assert clock.now() == start + timedelta(seconds=90)
    clock.advance(0)
    assert clock.now() == start + timedelta(seconds=90)
    for bad in (-1, 1.5, True):
        with pytest.raises(ValueError):
            clock.advance(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ControllableClock(datetime(2026, 1, 1))  # noqa: DTZ001
    with pytest.raises(ValueError):
        ControllableClock(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))))


def test_error_enforces_the_openapi_message_and_retryable_contract() -> None:
    assert Error("INTERNAL_ERROR", "x" * 256, True).retryable is True
    bad: list[tuple[object, object]] = [
        ("x" * 257, False),  # too long
        ("café", False),  # not printable ASCII
        ("line\nbreak", False),
        ("tab\t", False),
        (None, False),
        (b"bytes", False),
        ("ok", "yes"),  # retryable must be a real boolean
        ("ok", 1),
        ("ok", None),
    ]
    for message, retryable in bad:
        with pytest.raises(InvalidValue):
            Error("INTERNAL_ERROR", message, retryable)  # type: ignore[arg-type]
