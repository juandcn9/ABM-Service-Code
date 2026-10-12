# TASK-29 Tester report (merged revision)

**Task:** TASK-29 intact-volume restart only; no backup or disaster-recovery claim (NFR-08, TEST-32). **Merged commit:** e95fe56 (PR #117). **PR head:** 8f42e70. **Date:** 2026-10-11. **Role:** fresh-context Tester, read-only.

## Gates on e95fe56

| Gate | Result |
|---|---|
| pytest | `999 passed, 1 warning in 193.96s` |
| ruff check . | passed |
| ruff format --check . | 170 files already formatted |
| mypy src harness tests scripts | exit 0 |
| validate_governance.py | exit 0 |
| validate_toolchain.py | exit 0 |
| `git diff --stat 4acd135 e95fe56 -- src/` | empty |

## Scope

- The scan covers 45 files: README.md, Dockerfile, .dockerignore, docs/ (excluding docs/evidence), scripts/*.py, and the CI workflow. Every in-scope line that names a recovery term is disclaimed.
- The README Recovery section states restart against the intact mounted volume and lists backup, restore, disaster recovery, RPO and RTO as not claimed.

## Adversarial checks

| Input | Result |
|---|---|
| "Backups are supported and restored automatically." | flagged |
| "Disaster recovery is not claimed." | not flagged |
| "Backups are not supported." | not flagged |

## Mutants

| Mutant | Result |
|---|---|
| (a) Recovery section removed | caught by the statement test |
| (b) unqualified backup sentence added | caught by the term scan |
| (c) `scripts` removed from scope | caught only by the presence assertion, not the term scan |

## Findings

| ID | Class | Status |
|---|---|---|
| F-01 | Note | Accepted limit: a paraphrase without a listed term is not caught |
| F-02 | Note | Scripts coverage relies partly on one file's presence check (the term scan itself covers scripts/*.py) |
| F-03 | Note | README non-claim line was stale (says no runnable service); corrected in the Verified record PR |

## Verdict

**PASS.** No Blocker or Major findings.

## Not verified

- The CI run on the PR head (CI was green at head `8f42e70`; not re-run here).
- TASK-30 AWS reference (not present yet).
- Wording review of every docs file beyond the term scan.
