"""Opaque identifiers and UTC instants in their single canonical form (TEST-24, specs/04-api.md)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from abm.domain.errors import InvalidValue

# explicit ASCII classes: \w and \d would also match Unicode letters and digits
_OPAQUE_ID = re.compile(r"[-A-Za-z0-9._~]{1,128}")
_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def opaque_id(value: object) -> str:
    """1-128 URL-unreserved ASCII characters, returned unchanged; nothing is normalized or decoded."""
    if type(value) is not str or not _OPAQUE_ID.fullmatch(value):
        raise InvalidValue("identifier must be 1-128 URL-unreserved ASCII characters")
    return value


def parse_instant(value: object) -> datetime:
    """Strict YYYY-MM-DDTHH:MM:SSZ to an aware UTC datetime; any other shape is rejected."""
    if type(value) is not str or not _INSTANT.fullmatch(value):
        raise InvalidValue("timestamp must be a UTC instant like 2026-01-02T03:04:05Z")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:  # e.g. month 13 or 30 February
        raise InvalidValue("timestamp is not a real calendar instant") from exc


def format_instant(moment: datetime) -> str:
    """Aware UTC datetime to the stored form; sub-second precision is floored, never rounded up."""
    if moment.tzinfo is None or moment.utcoffset() != UTC.utcoffset(None):
        raise InvalidValue("instant must be timezone-aware UTC")
    # not strftime: %Y is not zero-padded for years below 1000 on glibc, which would break the
    # fixed 20-character stored form
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"
        f"T{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}Z"
    )
