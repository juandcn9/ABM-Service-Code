"""Controllable UTC clock port (specs/03-architecture.md section 8).

Read-only for the application. There is no wall-clock fallback: a missing or failing clock
rejects time-dependent work, and elapsed time alone never creates evidence (INV-12).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant as a timezone-aware UTC datetime."""
        ...
