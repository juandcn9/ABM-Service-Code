"""Runtime configuration from ABM_* environment variables (specs/07 section 2; TASK-27).

A missing or invalid setting raises ConfigError naming the setting only, never its value (TEST-27,
SEC-07). The demonstration container refuses a controlled clock: a served container has no test
harness to control time (a choice stricter than the Specs table; see the TASK-27 work item).
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from dataclasses import dataclass

MODES = frozenset({"development", "verification", "demonstration", "aws-reference"})
CLOCK_MODES = frozenset({"system", "controlled"})
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
# same bounds as persistence.database (checked by a unit test; config may not import abm layers)
MIN_BUSY_TIMEOUT_MS = 1
MAX_BUSY_TIMEOUT_MS = 60_000


class ConfigError(Exception):
    """Startup must stop. Carries the names of the offending settings only."""

    def __init__(self, names: list[str]) -> None:
        super().__init__("CONFIG_INVALID")
        self.names: tuple[str, ...] = tuple(sorted(names))


@dataclass(frozen=True)
class Settings:
    mode: str
    db_path: str
    log_level: str
    busy_timeout_ms: int
    clock_mode: str


def load_settings(env: Mapping[str, str]) -> Settings:
    """Parse and check every setting; collect all bad names before refusing to start."""
    bad: list[str] = []

    mode = env.get("ABM_MODE", "")
    if mode not in MODES:
        bad.append("ABM_MODE")

    db_path = env.get("ABM_DB_PATH", "")
    if not db_path or not pathlib.Path(db_path).is_absolute():
        bad.append("ABM_DB_PATH")

    log_level = env.get("ABM_LOG_LEVEL", "INFO")
    if log_level not in LOG_LEVELS:
        bad.append("ABM_LOG_LEVEL")

    busy = env.get("ABM_BUSY_TIMEOUT_MS", "5000")
    # at most six digits: longer text would be refused by int() with a traceback, not CONFIG_INVALID
    busy_timeout_ms = (
        int(busy) if busy.isascii() and busy.isdecimal() and len(busy) <= 6 else -1
    )
    if not MIN_BUSY_TIMEOUT_MS <= busy_timeout_ms <= MAX_BUSY_TIMEOUT_MS:
        bad.append("ABM_BUSY_TIMEOUT_MS")

    # the service always reads caller context from headers; the setting may only say so (SEC-01)
    ingress = env.get("ABM_TRUSTED_INGRESS", "")
    if ingress != "true" and not (ingress == "false" and mode != "demonstration"):
        bad.append("ABM_TRUSTED_INGRESS")

    clock_mode = env.get("ABM_CLOCK_MODE", "system")
    # only the system clock exists in this entry point; controlled is for the test harness
    if clock_mode != "system":
        bad.append("ABM_CLOCK_MODE")

    if bad:
        raise ConfigError(bad)
    return Settings(
        mode=mode,
        db_path=db_path,
        log_level=log_level,
        busy_timeout_ms=busy_timeout_ms,
        clock_mode=clock_mode,
    )
