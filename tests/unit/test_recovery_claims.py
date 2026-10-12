"""TASK-29 (TEST-32, NFR-08): the documentation and demo scripts make no backup, restore, disaster-recovery,
RPO, or RTO claim. Supported demonstration recovery is restart against the intact mounted volume.

Rule: every line that names a recovery term must also disclaim it (a negation or an explicit limit). The
evidence reports are excluded: they record mutant labels and test names, not product claims.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

TERMS = re.compile(
    r"\b(backups?|restor(e|es|ed|ing|ation)|disaster|RPO|RTO)\b", re.IGNORECASE
)
DISCLAIMER = re.compile(
    r"\b(no|not|none|never|without|outside|exclud\w*|unclaimed|absence|deferred|out of scope|limit\w*)\b",
    re.IGNORECASE,
)
SCOPE = [
    ROOT / "README.md",
    ROOT / "Dockerfile",
    ROOT / ".dockerignore",
    *sorted((ROOT / "docs").rglob("*.md")),
    *sorted((ROOT / "scripts").rglob("*.py")),
    *sorted((ROOT / ".github").rglob("*.yml")),
    *sorted((ROOT / "deploy").rglob("*.json")),
]
EXCLUDED = {ROOT / "docs" / "evidence"}

# The one exact-text exemption: the Gate 7 row names "backup/restore non-claims" verbatim (Specs
# quality-gates Gate 7). A GAP records that the Specs wording should later state the disclaimer in a
# form the guard can read. A line is exempt only when its stripped text equals the exact form below;
# any appended text is not exempt.
GATE7_ROW = (
    "| Gate 7 Operational | Container least privilege, mounted persistence, readiness, intact-volume restart, "
    "abrupt failure, and explicit backup/restore non-claims | Phase 4 cannot exit. |"
)
GATE7_EXACT = {
    ROOT / "docs" / "governance" / "repository-policy.md": GATE7_ROW,
    ROOT / "scripts" / "validate_governance.py": '"'
    + GATE7_ROW
    + '",',  # the validator's quoted copy
}


def is_exempt(path: pathlib.Path, line: str) -> bool:
    return path in GATE7_EXACT and line.strip() == GATE7_EXACT[path]


def in_scope() -> list[pathlib.Path]:
    return [
        path
        for path in SCOPE
        if path.is_file() and not any(parent in EXCLUDED for parent in path.parents)
    ]


def test_every_recovery_term_is_disclaimed_on_its_line():
    failures = []
    for path in in_scope():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            exempt = is_exempt(path, line)
            if TERMS.search(line) and not DISCLAIMER.search(line) and not exempt:
                failures.append(
                    f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}"
                )
    assert failures == [], "recovery claim without a disclaimer:\n" + "\n".join(
        failures
    )


def test_the_exemption_matches_exactly_one_line_in_each_file():
    for path, exact in GATE7_EXACT.items():
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        assert lines.count(exact) == 1, path


def test_an_appended_claim_on_the_exempt_row_is_not_exempt():
    claim = (
        " Nightly backups are restored within one hour (RTO 1h); this is a non-claim."
    )
    for path, exact in GATE7_EXACT.items():
        assert is_exempt(path, exact)
        assert not is_exempt(path, exact + claim)


def test_the_scan_reads_the_documentation_it_is_meant_to_cover():
    names = {path.name for path in in_scope()}
    assert {"README.md", "TASK-27.md", "check_container.py"} <= names


def test_the_supported_recovery_statement_is_present_in_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "intact" in readme and "restart" in readme
    assert re.search(r"Not claimed[^.\n]*backup", readme)
