"""Deterministic clock test double: time moves only when the harness advances it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class ControllableClock:
    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None or start.utcoffset() != UTC.utcoffset(None):
            raise ValueError("start must be timezone-aware UTC")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: int) -> None:
        if type(seconds) is not int or seconds < 0:
            raise ValueError("time only moves forward by whole seconds")
        self._now += timedelta(seconds=seconds)
