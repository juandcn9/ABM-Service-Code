"""TASK-27 image contract, read from the Dockerfile text (no docker needed): one worker, no access log,
UID 10001, and an exec-form ENTRYPOINT with no CMD that an image user could override to drop those flags."""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _instructions() -> str:
    # join backslash-continued physical lines into logical instructions
    return (ROOT / "Dockerfile").read_text(encoding="utf-8").replace("\\\n", " ")


def _entrypoint() -> list[str]:
    match = re.search(r"^ENTRYPOINT\s+(\[.*\])\s*$", _instructions(), re.MULTILINE)
    assert match, "ENTRYPOINT must be in exec (JSON array) form"
    return json.loads(match.group(1))


def test_the_entrypoint_runs_one_worker_without_an_access_log():
    argv = _entrypoint()
    assert "--no-access-log" in argv
    i = argv.index("--workers")
    assert argv[i + 1] == "1"


def test_the_image_runs_as_uid_10001():
    text = _instructions()
    user = re.search(r"^USER\s+(\S+)", text, re.MULTILINE)
    assert user and user.group(1) == "10001:10001"
    assert "--uid 10001" in text and "--gid 10001" in text


def test_no_cmd_can_replace_the_entrypoint_flags():
    # exec-form ENTRYPOINT with no CMD: a run-time argument is appended after the flags, never in
    # place of them, and the image declares no default argument list that could drop them
    assert not re.search(r"^CMD\b", _instructions(), re.MULTILINE)
    assert _entrypoint()[0] == "python"
