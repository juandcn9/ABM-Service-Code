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
    forbidden = {
        "private evidence path": "evidence/private/",
        "credential file": ".env",
    }
    ignore = texts.get(".gitignore", "")
    for label, token in forbidden.items():
        if token not in ignore:
            fail(f".gitignore lacks {label}: {token}")


def validate_workflow(texts: dict[str, str]) -> None:
    workflow = texts.get(".github/workflows/governance-ci.yml", "")
    if "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09" not in workflow:
        fail("checkout action is not pinned to the reviewed commit")
    if "python3 scripts/validate_governance.py" not in workflow:
        fail("workflow does not execute the governance validator")
    if "contents: read" not in workflow:
        fail("workflow permissions are not least privilege")


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
