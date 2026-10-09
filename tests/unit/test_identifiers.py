"""Opaque identifiers and UTC instants (TEST-24, domain part)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from abm.domain.errors import InvalidValue
from abm.domain.identifiers import format_instant, opaque_id, parse_instant


def test_identifiers_round_trip_unchanged() -> None:
    for good in ("a", "A-z_9.~", "x" * 128, "0123456789", "-", "~", "."):
        assert opaque_id(good) == good


def test_identifiers_reject_everything_outside_the_alphabet() -> None:
    bad = [
        "",
        "x" * 129,
        "has space",
        " lead",
        "trail ",
        "line\nbreak",
        "nl\n",  # a trailing newline must not slip through an end-anchor quirk
        "tab\t",
        "nul\x00",
        "slash/",
        "back\\slash",
        "pct%41",  # percent-encoded forms are not alternative spellings
        "q?",
        "hash#",
        "colon:",
        "at@",
        "plus+",
        "star*",
        "café",
        "١٢",  # Arabic-Indic digits are Unicode digits, not ASCII
        "Ａ",  # full-width A
        "emoji\U0001f600",
        "'; DROP TABLE accounts;--",
        None,
        1,
        b"abc",
        ["a"],
    ]
    for value in bad:
        with pytest.raises(InvalidValue):
            opaque_id(value)


def test_instants_parse_only_the_canonical_form() -> None:
    parsed = parse_instant("2026-10-09T12:34:56Z")
    assert parsed == datetime(2026, 10, 9, 12, 34, 56, tzinfo=UTC)
    assert format_instant(parsed) == "2026-10-09T12:34:56Z"
    bad = [
        "2026-10-09T12:34:56",  # no Z
        "2026-10-09T12:34:56+00:00",
        "2026-10-09 12:34:56Z",
        "2026-10-09T12:34:56.000Z",
        "2026-10-09T12:34Z",
        "2026-13-09T12:34:56Z",  # month 13
        "2026-02-30T12:34:56Z",  # not a real date
        "2026-10-09T24:00:00Z",
        "2026-10-09T12:34:56Z\n",
        " 2026-10-09T12:34:56Z",
        "٢026-10-09T12:34:56Z",
        "0000-01-01T00:00:00Z",
        "",
        None,
        1_800_000_000,
    ]
    for value in bad:
        with pytest.raises(InvalidValue):
            parse_instant(value)


def test_format_requires_aware_utc_and_floors_subseconds() -> None:
    assert (
        format_instant(datetime(2026, 1, 2, 3, 4, 5, 999_999, tzinfo=UTC))
        == "2026-01-02T03:04:05Z"
    )
    with pytest.raises(InvalidValue):
        format_instant(datetime(2026, 1, 2, 3, 4, 5))  # noqa: DTZ001
    with pytest.raises(InvalidValue):
        format_instant(
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2)))
        )
