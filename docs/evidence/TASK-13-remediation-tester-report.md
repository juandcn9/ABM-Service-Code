# TASK-13 remediation: independent re-check of 442bcb5 (Tester, second pass)

## Revision and chain
- origin/fix/task-13-remediation = 442bcb56e1094938262e51f38033ec53fd4992f6 (commit "docs: TASK-13 schedule Tester Minors F3 to F7 with owners and triggers")
- Parent = 1815afe5488c6753122b85ae8b865575ce7b872f (confirmed)
- origin/main = df97fa717fd619e37f9618e6d024c5b1a66df6ee
- `git diff --stat 1815afe 442bcb5`: `docs/work-items/TASK-13.md | 8 ++++++++`, 1 file changed, 8 insertions. Only the work item changed; no code change.
- Worktree: C:\Users\Admin\AppData\Local\Temp\abm-tester-13b, detached at 442bcb5. HEAD asserted equal to 442bcb5 before and after all gates; `git status` clean (only ignored caches and .venv).

## Fetch
- `git fetch origin +refs/heads/fix/task-13-remediation:... +refs/heads/main:...` exit 0. Ref advanced 1815afe..442bcb5.
- Fetch printed two `error: failed to delete '.git/worktrees/...': Permission denied` lines (ABM-Service-Code-task23, ABM-Service-Code-v1.9.6-pointer). Ref updates succeeded. Not a TASK-13 issue; see Observations.

## Environment
- Python 3.12.10 (local; CI pins 3.12.15, already declared as DV-02 in the work item).
- Venv: `py -3.12 -m venv .venv` inside the worktree, then `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock`, exit 0.
- Venv first created as `.venv-tester`; validator flagged it as an untracked non-ignored artifact (not a repo defect). Recreated as `.venv` (matched by `.gitignore:16 .venv/`) and re-ran every gate on it. Results below are from the `.venv` run only.

## Commands and exit codes (worktree at 442bcb5)
| Gate | Command | Exit | Result |
|---|---|---|---|
| Install | pip install --require-hashes --only-binary=:all: -r requirements-dev.lock | 0 | all pinned wheels installed |
| Tests | python -m pytest -p no:cacheprovider | 0 | 1103 passed, 1 warning (StarletteDeprecationWarning, httpx in test_container_entry.py; pre-existing, not TASK-13), 332 s |
| Lint | python -m ruff check . | 0 | All checks passed |
| Format | python -m ruff format --check . | 0 | 178 files already formatted |
| Types | python -m mypy src harness tests scripts | 0 | Success: no issues found in 99 source files |
| Governance | python scripts/validate_governance.py | 0 | TASK-01 VALIDATION PASSED; required files 11; Specs pointer v1.9.13 / fb32e092b7bab696c0dcad7ef76eb7ef7fa08c65 |

Note: the governance validator scans untracked-but-not-ignored files. A first run with a venv named `.venv-tester` failed (exit 1) for that reason alone; this is a local-environment artifact and is not a finding against 442bcb5.

Pytest on the first attempt (`.venv-tester`) was stopped deliberately and is not reported as a result.

## Scheduled-items check (docs/work-items/TASK-13.md, section "Scheduled items")
Compared against the Minor items in `docs/evidence/TASK-13-tester-report.md` on origin/main (lines 82-88).

| Finding | Owner in 442bcb5 | Trigger in 442bcb5 | Matches Tester report | Result |
|---|---|---|---|---|
| F3 return-side evidence reuse untested, M14 survives | Builder | next change to incoming return path or its tests | yes | PASS |
| F4 Implementation notes conflict with Completion and code (closed-account return); test count stale | Builder | next change to this work item | conflict yes; Tester also flagged stale PR status (not carried into the entry) | PASS with observation |
| F5 INV-10 negative-balance return path not exercised | Builder | next test building an outgoing debit before an incoming return | yes | PASS |
| F6 specs/04-api.md line 84 garbled, orphaned "API-06," (Specs-side) | Updater (Specs repo, outside Code repo) | next Specs documentation change | yes; Updater role is defined in docs/governance/deviations.md and TASK-05.md | PASS |
| F7 credit beyond cents bound becomes INTERNAL_ERROR (carried over) | Builder | next change to credit amount validation | yes | PASS |

All five findings have an owner and a trigger. F6 is correctly Updater, Specs-side.

## Findings
- Blocker: 0 open.
- Major: 0 open. Previous Major M1 (no scheduled items for F3-F7) is resolved by 442bcb5. Previous Major F1/F2 remain closed per the work item (not re-verified here beyond the suite passing).
- Minor: 5 open, all now scheduled (F3, F4, F5, F6, F7). None fixed by this commit, as intended.
- Observation:
  1. F4 entry omits the Tester's note that the PR status is stale relative to head. Only the test count and the Implementation/Completion conflict are carried.
  2. The "523" count in the Completion section is still stale; the entry notes this but the work item body is unchanged. Suite collects 1103 tests in total; the focused TASK-13 count was not re-derived in this pass.
  3. Fetch printed Permission-denied errors deleting stale worktree metadata in the shared .git (ABM-Service-Code-task23, ABM-Service-Code-v1.9.6-pointer). Ref updates succeeded; likely a locked worktree from another session. Local housekeeping only.
  4. Pytest ran on Python 3.12.10 locally, not CI's 3.12.15 (already DV-02).

## Not done
- No CI results checked (read-only; PR status not queried).
- Work item Completion section not edited (out of scope, read-only).
- Other testers' worktrees (ABM-Code-remed-01, -05, -13, -14) and their processes were not touched.

## Cleanup
- `git worktree remove --force C:\Users\Admin\AppData\Local\Temp\abm-tester-13b`: exit 0. Directory gone; worktree list no longer shows it.
- No commits, pushes, branch, ref or config changes made.

Verdict: PASS with findings
