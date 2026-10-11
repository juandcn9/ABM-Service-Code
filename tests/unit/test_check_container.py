"""TASK-27 container check decision (TEST-33): a bad container must fail, a good one must pass."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_container import container_failures  # type: ignore[import-not-found]


def test_a_non_root_read_only_container_with_a_writable_volume_passes():
    assert container_failures("10001", app_write_rc=1, data_write_rc=0) == []


def test_a_root_process_fails():
    assert container_failures("0", app_write_rc=1, data_write_rc=0) == [
        "process UID is 0, expected 10001 (not root)"
    ]


def test_a_writable_application_layer_fails():
    assert container_failures("10001", app_write_rc=0, data_write_rc=0) == [
        "application layer is writable"
    ]


def test_an_unwritable_data_volume_fails():
    assert container_failures("10001", app_write_rc=1, data_write_rc=1) == [
        "data volume is not writable"
    ]
