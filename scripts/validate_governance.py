from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_SPEC = {
    "spec_repository": "https://github.com/juandcn9/ABM-Service-Specs",
    "spec_version": "v1.0.1",
    "spec_commit": "5d1cd410399a6fb0154a0117728c409cc7f2ec91",
}
REQUIRED_FILES = {
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "SPEC_VERSION",
    ".gitignore",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/work-item.md",
    ".github/workflows/governance-ci.yml",
    "docs/governance/repository-policy.md",
    "docs/work-items/TASK-01.md",
    "scripts/validate_governance.py",
}
TEXT_SUFFIXES = {
    ".example",
    ".lock",
    ".md",
    ".python-version",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    "",
}
PLACEHOLDER_PATTERN = (
    r"\b(?:" + "|".join(("TO" + "DO", "T" + "BD", "FIX" + "ME", "X" + "XX")) + r")\b"
)
REQUIRED_IGNORE_LINES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.log",
    ".venv/",
    "__pycache__/",
    "evidence/private/",
    "*.exe",
    "*.dll",
)
ALLOWED_STATUS = {
    "Draft",
    "Blocked",
    "Ready for JDC review",
    "Approved",
    "Implemented",
    "Verified",
}
# exact field labels of the Specs templates (templates/pull-request.md and templates/work-item.md)
PR_FIELDS = (
    "- Approved Specs version/SHA:",
    "- TASK:",
    "- BT/FR/INV/NFR/SEC/API/DATA/TEST:",
    "- DEC-nnnn/GAP-nnnn/RISK-nnnn:",
    "- Behavior:",
    "- Persistence/migration:",
    "- API compatibility:",
    "- Security/data handling:",
    "- Operations/recovery:",
    "- Explicit non-claims:",
    "- Focused tests:",
    "- Full gates:",
    "- Concurrency/fault evidence:",
    "- Container/restart/recovery evidence, if applicable:",
    "- Secret/prohibited-data scan:",
    "- Evidence manifest or CI links:",
    "- Independent reviewer:",
    "- Blocker/Major findings and resolution:",
    "- Remaining Minor/Observation items:",
    "- [ ] Branch is current and checks are green.",
    "- [ ] Requirement, contract, test, and task trace is complete.",
    "- [ ] No uncontrolled placeholder, secret, real customer data, or unsupported claim.",
    "- [ ] Required approvals apply to this exact commit.",
    "- [ ] Merge will not change the approved commit.",
)
WORK_ITEM_FIELDS = (
    "- Specs version and exact SHA:",
    "- TASK and affected BT/FR/INV/NFR/SEC/API/DATA/TEST IDs:",
    "- Decision, gap, or risk records:",
    "- Author/owner:",
    "- Objective:",
    "- Included files/components:",
    "- Explicit exclusions:",
    "- Dependencies and entry gate:",
    "- Focused tests:",
    "- Required broader gates:",
    "- Failure, concurrency, authorization, and recovery cases:",
    "- Documentation/trace updates:",
    "- Code commit/PR:",
    "- Commands/checks and results:",
    "- Review findings/resolution:",
    "- Residual risks:",
    "- Next safe action:",
)
POLICY_TOPICS = (
    "## Human approval for risky actions",
    "## Findings and severity",
    "## Lifecycle status values",
    "## Approval and merge authority",
    "force-push",
    "self-approval is prohibited",
    "may not be downgraded",
    "Blocker",
    "Verified",
)
FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)


def relative(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    # Tracked plus untracked-but-not-ignored files: a force-added file in an ignored
    # directory (.venv, caches) is tracked, so it can no longer escape the scan.
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    for entry in sorted(set(listed.split("\0")) - {""}):
        path = ROOT / entry
        if not path.is_file():
            continue
        name = relative(path)
        if path.suffix.lower() not in TEXT_SUFFIXES:
            fail(f"unexpected non-text artifact: {name}")
            continue
        try:
            texts[name] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(f"non-UTF-8 file: {name}")
    missing = REQUIRED_FILES - set(texts)
    if missing:
        fail(f"missing required files: {sorted(missing)}")
    return texts


def validate_spec_pointer(texts: dict[str, str]) -> None:
    parsed: dict[str, str] = {}
    for line in texts.get("SPEC_VERSION", "").splitlines():
        if not line or "=" not in line:
            fail("SPEC_VERSION contains a malformed line")
            continue
        key, value = line.split("=", 1)
        if key in parsed:
            fail(f"SPEC_VERSION duplicates {key}")
        parsed[key] = value
    if parsed != EXPECTED_SPEC:
        fail(f"SPEC_VERSION mismatch: {parsed}")
    readme = texts.get("README.md", "")
    for value in EXPECTED_SPEC.values():
        if value not in readme:
            fail(f"README omits approved Specs pointer value: {value}")
    for name in ("docs/governance/repository-policy.md", "docs/work-items/TASK-01.md"):
        body = texts.get(name, "")
        for key in ("spec_version", "spec_commit"):
            if EXPECTED_SPEC[key] not in body:
                fail(f"{name} omits approved Specs pointer value: {EXPECTED_SPEC[key]}")


def validate_documents(texts: dict[str, str]) -> None:
    required_headings = {
        "README.md": ("## Authority", "## Current scope", "## Non-claims"),
        "docs/governance/repository-policy.md": (
            "## Authority and scope",
            "## Pull-request gate",
            "## Review independence",
        ),
        "docs/work-items/TASK-01.md": (
            "## Authority",
            "## Scope",
            "## Acceptance evidence",
            "## Completion",
        ),
        ".github/pull_request_template.md": (
            "## Authority and trace",
            "## Evidence",
            "## Review",
            "## Merge checklist",
        ),
    }
    for name, headings in required_headings.items():
        body = texts.get(name, "")
        for heading in headings:
            if heading not in body:
                fail(f"{name} lacks heading: {heading}")
    pr_lines = {
        ln.strip()
        for ln in texts.get(".github/pull_request_template.md", "").splitlines()
    }
    for field in PR_FIELDS:
        if field not in pr_lines:
            fail(f"pull-request template lacks Specs field: {field}")
    ponytail_lines = [ln for ln in pr_lines if ln.startswith("- Ponytail")]
    if not ponytail_lines or not all(
        "`full` mode" in ln and "`ponytail-review`" in ln for ln in ponytail_lines
    ):
        fail("pull-request template Ponytail line lacks full mode or ponytail-review")
    item_lines = {
        ln.strip()
        for ln in texts.get(".github/ISSUE_TEMPLATE/work-item.md", "").splitlines()
    }
    for field in WORK_ITEM_FIELDS:
        if field not in item_lines:
            fail(f"work-item template lacks Specs field: {field}")
    policy = texts.get("docs/governance/repository-policy.md", "")
    for topic in POLICY_TOPICS:
        if topic not in policy:
            fail(f"repository policy omits required control: {topic}")
    for name, body in texts.items():
        if name.startswith("docs/work-items/") and name.endswith(".md"):
            for value in re.findall(r"(?m)^\*\*Status:\*\*\s*(.+?)\s*$", body):
                if value not in ALLOWED_STATUS:
                    fail(f"{name}: uncontrolled lifecycle status: {value}")
    controlled = "\n".join(texts.values())
    if re.search(PLACEHOLDER_PATTERN, controlled, re.IGNORECASE):
        fail("uncontrolled placeholder found")


def validate_safety(texts: dict[str, str]) -> None:
    combined = "\n".join(texts.values())
    patterns = {
        "private key": "-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
        "GitHub token": r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b",
        "assigned credential": r"(?i)\b(?:password|passwd|api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        "bearer token": r"(?i)\bBearer\s+[A-Za-z0-9._~-]{20,}\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, combined):
            fail(f"probable secret detected: {label}")
    for line_no, number in _card_like_numbers(combined):
        fail(f"probable payment card number (Luhn-valid {len(number)} digits)")
    for name, body in texts.items():
        if "\x00" in body:
            fail(f"NUL byte in text file: {name}")
    ignore_lines = {ln.strip() for ln in texts.get(".gitignore", "").splitlines()}
    for required in REQUIRED_IGNORE_LINES:
        if required not in ignore_lines:
            fail(f".gitignore lacks an active line: {required}")


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        n = int(char)
        if index % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _card_like_numbers(text: str) -> list[tuple[int, str]]:
    found = []
    for match in re.finditer(r"(?<![\w.])\d{13,19}(?![\w.])", text):
        if _luhn(match.group()):
            found.append((match.start(), match.group()))
    return found


def validate_workflow(texts: dict[str, str]) -> None:
    workflow = texts.get(".github/workflows/governance-ci.yml", "")
    lines = workflow.splitlines()
    if not re.search(r"(?m)^permissions:\s*\n  contents: read\s*$", workflow):
        fail("workflow permissions are not exactly contents: read")
    for bad in (
        "pull_request_target",
        "contents: write",
        "continue-on-error",
        "|| true",
    ):
        if bad in workflow:
            fail(f"workflow contains forbidden text: {bad}")
    uses = [ln for ln in lines if re.match(r"^\s*(?:- )?uses:", ln)]
    if not uses:
        fail("workflow has no uses: lines")
    for ln in uses:
        if not re.match(r"^\s*(?:- )?uses: [\w./-]+@[0-9a-f]{40}(?:\s+#.*)?$", ln):
            fail(f"workflow action is not pinned to a full commit: {ln.strip()}")
    if not any(
        re.match(r"^\s+run: python3? scripts/validate_governance\.py\s*$", ln)
        for ln in lines
    ):
        fail("workflow does not execute the governance validator as an active step")


def main() -> int:
    texts = load_texts()
    validate_spec_pointer(texts)
    validate_documents(texts)
    validate_safety(texts)
    validate_workflow(texts)
    if FAILURES:
        print("TASK-01 VALIDATION FAILED")
        for item in FAILURES:
            print(f"- {item}")
        return 1
    print("TASK-01 VALIDATION PASSED")
    print(f"- required files: {len(REQUIRED_FILES)}")
    print("- Specs pointer: v1.0.1 / 5d1cd410399a6fb0154a0117728c409cc7f2ec91")
    print(
        "- governance headings, workflow pin, placeholders, and secret patterns: passed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
