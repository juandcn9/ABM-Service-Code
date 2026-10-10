from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_SPEC = {
    "spec_repository": "https://github.com/juandcn9/ABM-Service-Specs",
    "spec_version": "v1.6.1",
    "spec_commit": "550eb07f7112ec72d27bc4f0c4651cdd5ff98b63",
}
REVIEWED_GITHUB_FILES = {
    ".github/workflows/governance-ci.yml",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/work-item.md",
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
    ".sql",
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
# Whole-file digest (LF-normalized) of the CI workflow. Any change to the workflow, including a new
# step, permission, trigger, or condition, must update this value in the same reviewed commit, so
# "no required check is advisory" cannot be weakened silently.
EXPECTED_WORKFLOW_SHA256 = (
    "919232c15511968f64914d038261ad0acdf72c563dd5c7256fa0b9faec66a3bb"
)
# paths that must be ignored by git, and one that must stay trackable
IGNORED_SAMPLES = (
    ".env",
    ".env.local",
    "src/.env",
    "x.pem",
    "src/deep/x.pem",
    "x.key",
    "x.p12",
    "x.pfx",
    "x.db",
    "x.sqlite",
    "x.sqlite3",
    "x.db-wal",
    "x.db-shm",
    "x.log",
    "a.exe",
    "a.dll",
    "evidence/private/x",
    ".venv/x",
    "venv/x",
    "env/x",
    "__pycache__/x.pyc",
    "a/b/__pycache__/x.txt",
    "x.pyc",
    ".pytest_cache/x",
    ".mypy_cache/x",
    "a/.mypy_cache/x",
    ".ruff_cache/x",
    "build/x",
    "dist/x",
    "x.egg-info/x",
    ".coverage",
    "htmlcov/x",
    ".vscode/x",
    ".idea/x",
    ".DS_Store",
    "Thumbs.db",
)
TRACKABLE_SAMPLES = (".env.example", "src/abm/x.py")
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
POLICY_PHRASES = (
    "an exploitable or control-bypass defect",
    "Blocked pending explicit JDC acceptance",
    "recorded as future work with a production non-claim",
    "unreviewed binaries",
    "plugin or tool telemetry",
    "preserve sanitized evidence",
    "Cursor",
    "Minor documentation findings",
    "single maintainer",
    "merge, tag, or implementation step",
    "docs/short-purpose",
    "documented placeholders",
    "short-lived",
    "is incomplete",
    "workflow digest",
)
POLICY_BULLETS = (
    "- **Blocker:**",
    "- **Major:**",
    "- **Minor:**",
    "- **Observation:**",
)
STATUS_ROWS = (
    "| Draft |",
    "| Blocked |",
    "| Ready for JDC review |",
    "| Approved |",
    "| Implemented |",
    "| Verified |",
)
WORK_ITEM_SENTENCE = "A normative ambiguity becomes GAP-nnnn and pauses affected work."
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


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_RAW_HTML = re.compile(
    r"<\s*/?\s*(?:pre|div|span|details|summary|script|style|iframe|template|textarea)\b",
    re.IGNORECASE,
)


def visible(text: str) -> str:
    """Markdown as a reader sees it: HTML comments and fenced code blocks removed.

    Both backtick and tilde fences are handled; a closing fence must use the same character and
    be at least as long as the opening one; an unterminated fence hides the rest of the file.
    """
    lines: list[str] = []
    fence: str | None = None
    for line in _HTML_COMMENT.sub("", text).splitlines():
        if fence is None:
            opening = _FENCE_OPEN.match(line)
            if opening:
                fence = opening.group(1)
            else:
                lines.append(line)
            continue
        bare = line.strip()
        if (
            _FENCE_OPEN.match(line)
            and set(bare) == {fence[0]}
            and len(bare) >= len(fence)
        ):
            fence = None
    return "\n".join(lines)


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
        body = visible(texts.get(name, ""))
        for heading in headings:
            if not re.search(rf"(?m)^{re.escape(heading)}\s*$", body):
                fail(f"{name} lacks heading: {heading}")
    # fields must start at column 0 (an indented line is a code block, not a field)
    pr_lines = {
        ln.rstrip()
        for ln in visible(
            texts.get(".github/pull_request_template.md", "")
        ).splitlines()
    }
    for field in PR_FIELDS:
        if field not in pr_lines:
            fail(f"pull-request template lacks Specs field: {field}")
    ponytail_lines = [ln for ln in pr_lines if ln.startswith("- Ponytail")]
    if not ponytail_lines or not all(
        "`full` mode" in ln and "`ponytail-review`" in ln for ln in ponytail_lines
    ):
        fail("pull-request template Ponytail line lacks full mode or ponytail-review")
    item_text = visible(texts.get(".github/ISSUE_TEMPLATE/work-item.md", ""))
    item_lines = {ln.rstrip() for ln in item_text.splitlines()}
    for field in WORK_ITEM_FIELDS:
        if field not in item_lines:
            fail(f"work-item template lacks Specs field: {field}")
    if WORK_ITEM_SENTENCE not in item_text:
        fail("work-item template lacks the GAP-nnnn escalation sentence")
    policy = visible(texts.get("docs/governance/repository-policy.md", ""))
    for topic in POLICY_TOPICS:
        if topic not in policy:
            fail(f"repository policy omits required control: {topic}")
    for phrase in POLICY_PHRASES:
        if phrase not in policy:
            fail(f"repository policy omits required clause: {phrase}")
    policy_lines = [ln.rstrip() for ln in policy.splitlines()]
    for bullet in POLICY_BULLETS:
        if not any(ln.startswith(bullet) for ln in policy_lines):
            fail(f"repository policy omits severity definition: {bullet}")
    for row in STATUS_ROWS:
        if not any(ln.startswith(row) for ln in policy_lines):
            fail(f"repository policy omits lifecycle status row: {row}")
    for name, body in texts.items():
        shown = visible(body)
        governed = name in (
            "README.md",
            "docs/governance/repository-policy.md",
            ".github/pull_request_template.md",
            ".github/ISSUE_TEMPLATE/work-item.md",
        ) or name.startswith("docs/work-items/")
        if governed and _RAW_HTML.search(shown):
            fail(f"{name}: raw HTML elements are not allowed in governance documents")
        if not name.endswith(".md"):
            continue
        statuses = [
            ln
            for ln in shown.splitlines()
            if re.match(r"^[*_ ]{0,4}Status[*_ ]{0,4}:", ln, re.IGNORECASE)
        ]
        for line in statuses:
            match = re.fullmatch(r"\*\*Status:\*\* (.+?)\s*", line)
            if not match or match.group(1) not in ALLOWED_STATUS:
                fail(
                    f"{name}: malformed or uncontrolled status line: {line.strip()[:60]}"
                )
        if name.startswith("docs/work-items/") and len(statuses) != 1:
            fail(
                f"{name}: expected exactly one lifecycle status line, found {len(statuses)}"
            )
    controlled = "\n".join(texts.values())
    if re.search(PLACEHOLDER_PATTERN, controlled, re.IGNORECASE):
        fail("uncontrolled placeholder found")


def validate_safety(texts: dict[str, str]) -> None:
    combined = "\n".join(texts.values())
    patterns = {
        "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "AWS access key": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        "GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,})\b",
        "Slack token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
        "payment-provider live key": r"\b[sr]k_live_[A-Za-z0-9]{10,}",
        "JSON web token": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "credentials in a URL": r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@",
        "assigned credential": r"(?i)\b(?:password|passwd|api[_-]?key|secret[_-]?key)[\"']?\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        "unquoted credential": r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)\w*\s*[:=]\s*[\"']?(?=[^\s\"']*\d)(?=[^\s\"']*[A-Za-z])[^\s\"']{12,}",
        "bearer token": r"(?i)\bBearer\s+(?=[A-Za-z0-9._~-]*\d)[A-Za-z0-9._~-]{20,}\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, combined):
            fail(f"probable secret detected: {label}")
    for line_no, number in _card_like_numbers(combined):
        fail(f"probable payment card number (Luhn-valid {len(number)} digits)")
    for name, body in texts.items():
        if "\x00" in body:
            fail(f"NUL byte in text file: {name}")
    validate_ignore(texts)


def validate_ignore(texts: dict[str, str]) -> None:
    """Use git's own matching on this repository's .gitignore alone: negations, spacing, case,
    and nested files cannot fool it, and no local or global git setting can mask a gap."""
    nested = [n for n in texts if n.endswith(".gitignore") and n != ".gitignore"]
    if nested:
        fail(f"nested .gitignore files are not allowed: {sorted(nested)}")
    ignored = _git_ignored(
        texts.get(".gitignore", ""), IGNORED_SAMPLES + TRACKABLE_SAMPLES
    )
    for sample in IGNORED_SAMPLES:
        if sample not in ignored:
            fail(f".gitignore does not ignore: {sample}")
    for sample in TRACKABLE_SAMPLES:
        if sample in ignored:
            fail(f".gitignore wrongly ignores a file the repository needs: {sample}")


def _git_ignored(rules: str, paths: tuple[str, ...]) -> set[str]:
    """The subset of paths that git ignores under these rules, in a fresh empty repository with
    global and system configuration disabled and case-sensitive matching (as on Linux CI)."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
        )
    }
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "XDG_CONFIG_HOME": os.devnull,
        }
    )
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run(
            ["git", "init", "-q", scratch], capture_output=True, check=True, env=env
        )
        pathlib.Path(scratch, ".gitignore").write_bytes(rules.encode("utf-8"))
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.ignoreCase=false",
                "-c",
                "core.excludesFile=",
                "check-ignore",
                "--no-index",
                "--stdin",
            ],
            cwd=scratch,
            # bytes, not text mode: Windows text mode would turn each newline into CRLF
            input=("\n".join(paths) + "\n").encode("utf-8"),
            capture_output=True,
            check=False,
            env=env,
        )
    output = result.stdout.decode("utf-8", errors="replace")
    return {line.strip() for line in output.splitlines() if line.strip()}


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        n = int(char)
        if index % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


_CARD_SHAPES = (
    r"(?<![\w.-])\d{15,19}(?![\w.-])",  # contiguous
    r"(?<![\w.-])\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}(?![\w-])",  # 4-4-4-x groups
    r"(?<![\w.-])\d{4}([ -])\d{6}\1\d{5}(?![\w-])",  # 4-6-5 groups
)


def _card_like_numbers(text: str) -> list[tuple[int, str]]:
    """Luhn-valid numbers shaped like payment cards: 15 to 19 contiguous digits, or the usual
    4-4-4-x and 4-6-5 groupings with spaces or dashes. Dates and 13 or 14 digit numbers such as
    millisecond timestamps do not have these shapes."""
    found = []
    for shape in _CARD_SHAPES:
        for match in re.finditer(shape, text):
            digits = re.sub(r"\D", "", match.group())
            if 13 <= len(digits) <= 19 and _luhn(digits):
                found.append((match.start(), digits))
    return found


def validate_workflow(texts: dict[str, str]) -> None:
    for name in texts:
        if name.startswith(".github/") and name not in REVIEWED_GITHUB_FILES:
            fail(
                f"unreviewed file under .github (workflows, actions, or settings): {name}"
            )
    workflow = texts.get(".github/workflows/governance-ci.yml", "")
    digest = hashlib.sha256(workflow.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    if digest != EXPECTED_WORKFLOW_SHA256:
        fail(
            "CI workflow differs from the reviewed version; a deliberate change must update "
            "EXPECTED_WORKFLOW_SHA256 in the same commit"
        )
    # readable checks that explain what the digest protects
    lines = workflow.splitlines()
    if not re.search(r"(?m)^permissions:\s*\n  contents: read\s*\n\s*\n", workflow):
        fail("workflow permissions are not exactly contents: read")
    for bad in (
        "pull_request_target",
        "contents: write",
        "continue-on-error",
        "|| true",
        "permissions: write-all",
    ):
        if bad in workflow:
            fail(f"workflow contains forbidden text: {bad}")
    if re.search(r"(?m)^[ \t]+permissions:", workflow) or re.search(
        r"(?m)^[ \t]+if:", workflow
    ):
        fail("workflow has a job-level permissions or condition key")
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
    print("- Specs pointer: v1.6.1 / 550eb07f7112ec72d27bc4f0c4651cdd5ff98b63")
    print(
        "- governance headings, workflow pin, placeholders, and secret patterns: passed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
