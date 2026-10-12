# TASK-01 Independent Tester Report (Tester 01g)

## Revision and chain
- origin/fix/task-01-remediation: fe28fd9857869a679b91f49fe00449c51f9f0ed2 (verified after fetch)
- Parent: 09d78d25b5abc707457e43e85381b5e5072e6fd2 (Tester PASS with findings, Minor 1)
- Grandparent chain: ced78d4, 4ab685a
- Fetch: `git fetch origin +refs/heads/fix/task-01-remediation:... +refs/heads/main:...` exit 0. Fetch also printed two "failed to delete .git/worktrees/... Permission denied" lines during ref pruning (see Observations); fetch itself succeeded.
- Worktree: detached at fe28fd9, path C:\Users\Admin\AppData\Local\Temp\abm-tester-01g. HEAD asserted fe28fd9 before the run and after the run.
- Venv: C:\Users\Admin\AppData\Local\Temp\abm-tester-01g-venv (Python 3.12.10), outside the worktree. Worktree `git status --porcelain` was empty throughout, including after the mutation restore.

## Diff check (09d78d2..fe28fd9)
- `git diff --stat`: `tests/unit/test_recovery_claims.py | 24 ------------------------`, 1 file changed, 24 deletions.
- `git diff --numstat`: `0  24  tests/unit/test_recovery_claims.py`. Removal-only, one file, as stated.

## Commands and exit codes
| Command | Exit | Result |
|---|---|---|
| `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock` | 0 | All pins installed, hashes verified |
| `pytest -p no:cacheprovider` (full suite) | 0 | 1228 passed, 1 warning (StarletteDeprecationWarning, httpx); 470 s |
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 178 files already formatted |
| `mypy src harness tests scripts` | 0 | Success: no issues found in 99 source files |
| `python scripts/validate_governance.py` | 0 | TASK-01 VALIDATION PASSED (11 required files; Specs v1.9.13 / fb32e092) |
| `pytest tests/unit/test_recovery_claims.py -v` | 0 | 5 passed |

## Guard file inspection (tests/unit/test_recovery_claims.py)
- `is_exempt(path, line)` returns `path in GATE7_EXACT and line.strip() == GATE7_EXACT[path]`. This is an exact-line match, not a prefix or substring match.
- `GATE7_EXACT` has two entries: `docs/governance/repository-policy.md` (the Gate 7 row) and `scripts/validate_governance.py` (the quoted copy with trailing `",`).
- The appended-claim test (`test_an_appended_claim_on_the_exempt_row_is_not_exempt`) is present and passes.
- The 5 tests passed: every_recovery_term_is_disclaimed_on_its_line, the_exemption_matches_exactly_one_line_in_each_file, an_appended_claim_on_the_exempt_row_is_not_exempt, the_scan_reads_the_documentation_it_is_meant_to_cover, the_supported_recovery_statement_is_present_in_the_readme.
- The duplicated SCOPE/EXCLUDED/GATE7_PATHS definitions are gone; only one definition of each remains.

## Mutation test
- Target: docs/governance/repository-policy.md, Gate 7 row (line 103). The row string occurred exactly once.
- Backup taken to C:\Users\Admin\AppData\Local\Temp\abm-tester-01g-policy.bak. Backup SHA-256 = pre-mutation SHA-256 = 5D87065BA1048301EFB6E07E16285AB3B600BF523641321EA493E501112B6881.
- Appended: " Nightly backups are restored within one hour (RTO 1h); this is a non-claim." Mutated SHA-256 = ECDA6CE422070FEE17B7603C10B6898F18E2CF1E55D193253A776EFAA315263F.
- Result: `pytest tests/unit/test_recovery_claims.py` exit 1, 2 failed, 3 passed. Failures: test_every_recovery_term_is_disclaimed_on_its_line and test_the_exemption_matches_exactly_one_line_in_each_file. The exact-line exemption rejected the mutated row.
- Restored from backup. Restored SHA-256 = 5D87065BA1048301EFB6E07E16285AB3B600BF523641321EA493E501112B6881, which matches the pre-mutation hash. `git status --porcelain` empty afterwards.

## Cleanup
- `git worktree remove --force` on the tester worktree: exit 0. Path no longer exists. origin/fix/task-01-remediation still resolves to fe28fd9.
- Venv and backup file left in C:\Users\Admin\AppData\Local\Temp (outside the repo).
- No commits, pushes, or ref/config changes made. The existing checkout was not edited.

## Findings

### Blocker: 0
### Major: 0

### Minor: 0
- Prior Tester Minor (duplicated SCOPE block in test_recovery_claims.py) is resolved in fe28fd9 by the 24-line removal-only cleanup.

### Observations
1. `scripts/validate_governance.py` still passes (exit 0) after the appended-claim mutation. The governance validator does not check for appended text on the Gate 7 row; only the pytest guard catches it. This is expected by design, but means `validate_governance.py` alone is not a sufficient gate for this non-claim.
2. The fetch printed "failed to delete '.git/worktrees/ABM-Service-Code-task23' / '...-v1.9.6-pointer': Permission denied" during auto-prune. Environment-level, not a code defect; fetch succeeded. The existing checkout's stale worktree metadata may need cleanup by the owner.
3. The full pytest run emits one StarletteDeprecationWarning (httpx with starlette.testclient) in tests/integration/test_container_entry.py. Not a failure.

Verdict: PASS with findings
