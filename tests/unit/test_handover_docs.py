"""TASK-38 (DEC-0086): the local-handover runbook exists, is linked from the README, and keeps its safety statements."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "handover" / "local-windows-runbook.md"


def test_runbook_is_linked_from_the_readme() -> None:
    assert "docs/handover/local-windows-runbook.md" in (ROOT / "README.md").read_text(
        encoding="utf-8"
    )


def test_runbook_keeps_the_trust_warning_and_the_start_settings() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "Never expose it to untrusted callers or the internet",
        "-p 127.0.0.1:8000:8000",
        "ABM_MODE=demonstration",
        "ABM_TRUSTED_INGRESS=true",
        "ABM_CLOCK_MODE=system",
        "docker volume rm abm-data",
        "/health/ready",
    ):
        assert required in text
