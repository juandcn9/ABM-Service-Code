"""TASK-27 configuration parser: every setting, each rejected value, names-only errors (TEST-27, SEC-07)."""

from __future__ import annotations

import pathlib

import pytest

from abm.config import (
    MAX_BUSY_TIMEOUT_MS,
    MIN_BUSY_TIMEOUT_MS,
    ConfigError,
    load_settings,
)
from abm.persistence.database import (
    MAX_BUSY_TIMEOUT_MS as DB_MAX,
)
from abm.persistence.database import (
    MIN_BUSY_TIMEOUT_MS as DB_MIN,
)

DB = str(pathlib.Path("/data/abm.sqlite3").absolute())
GOOD = {
    "ABM_MODE": "demonstration",
    "ABM_DB_PATH": DB,
    "ABM_TRUSTED_INGRESS": "true",
}


def names_of(env: dict[str, str]) -> tuple[str, ...]:
    with pytest.raises(ConfigError) as info:
        load_settings(env)
    return info.value.names


def test_a_complete_demonstration_environment_loads_with_defaults():
    settings = load_settings(GOOD)
    assert settings.mode == "demonstration"
    assert settings.db_path == DB
    assert settings.log_level == "INFO"
    assert settings.busy_timeout_ms == 5000
    assert settings.clock_mode == "system"


def test_bounds_match_the_persistence_layer():
    assert (MIN_BUSY_TIMEOUT_MS, MAX_BUSY_TIMEOUT_MS) == (DB_MIN, DB_MAX)


@pytest.mark.parametrize("missing", ["ABM_MODE", "ABM_DB_PATH", "ABM_TRUSTED_INGRESS"])
def test_a_missing_required_setting_is_named(missing):
    env = {k: v for k, v in GOOD.items() if k != missing}
    assert names_of(env) == (missing,)


@pytest.mark.parametrize(
    "name, value",
    [
        ("ABM_MODE", "production"),
        ("ABM_DB_PATH", "relative/abm.sqlite3"),
        ("ABM_DB_PATH", ""),
        ("ABM_LOG_LEVEL", "TRACE"),
        ("ABM_BUSY_TIMEOUT_MS", "0"),
        ("ABM_BUSY_TIMEOUT_MS", "60001"),
        ("ABM_BUSY_TIMEOUT_MS", "-5"),
        ("ABM_BUSY_TIMEOUT_MS", "5s"),
        ("ABM_TRUSTED_INGRESS", "yes"),
        ("ABM_CLOCK_MODE", "wall"),
    ],
)
def test_each_invalid_value_names_only_its_setting(name, value):
    assert names_of({**GOOD, name: value}) == (name,)


def test_the_error_text_never_contains_a_value():
    canary = "canary-value-123-do-not-print"
    with pytest.raises(ConfigError) as info:
        load_settings({**GOOD, "ABM_LOG_LEVEL": canary})
    assert canary not in str(info.value) and canary not in repr(info.value.names)


def test_all_bad_names_are_collected_before_refusing():
    env = {"ABM_MODE": "nope", "ABM_TRUSTED_INGRESS": "maybe"}
    assert names_of(env) == ("ABM_DB_PATH", "ABM_MODE", "ABM_TRUSTED_INGRESS")


def test_a_controlled_clock_is_refused_in_the_demonstration_container():
    assert names_of({**GOOD, "ABM_CLOCK_MODE": "controlled"}) == ("ABM_CLOCK_MODE",)


def test_a_controlled_clock_is_allowed_in_verification():
    env = {**GOOD, "ABM_MODE": "verification", "ABM_CLOCK_MODE": "controlled"}
    assert load_settings(env).clock_mode == "controlled"


def test_trusted_ingress_false_is_refused_in_the_demonstration_container():
    assert names_of({**GOOD, "ABM_TRUSTED_INGRESS": "false"}) == (
        "ABM_TRUSTED_INGRESS",
    )


def test_trusted_ingress_false_is_allowed_outside_the_demonstration():
    assert (
        load_settings(
            {**GOOD, "ABM_MODE": "development", "ABM_TRUSTED_INGRESS": "false"}
        ).mode
        == "development"
    )


def test_a_non_ascii_digit_busy_timeout_is_refused():
    assert names_of({**GOOD, "ABM_BUSY_TIMEOUT_MS": "٥٠٠٠"}) == ("ABM_BUSY_TIMEOUT_MS",)
