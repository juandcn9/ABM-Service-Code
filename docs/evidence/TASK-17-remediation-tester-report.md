# TASK-17 remediation: independent Tester report

## Pinned revision
- Tested revision: 1924c28 (`test: TASK-17 401 is not stored and the same key is evaluated fresh`), branch fix/task-17-401
- Parent of 1924c28: b81cee6 (`Merge pull request #122 from juandcn9/docs/task-30-verified`). Confirmed.
- origin/main (`git ls-remote https://github.com/juandcn9/ABM-Service-Code.git refs/heads/main`): b81cee6df269ec8141377496634bb852fce8cb1f. Unchanged from the expected value.
- Worktree HEAD asserted as 1924c28 before and after the run. Worktree removed with `worktree remove --force`; the path no longer exists. The main checkout and other worktrees were not modified.

## Environment
- Python 3.12.10 (`py -3.12`), venv `.venv` inside the worktree.
- Install: `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock` (exit 0). Then `pip install -e . --no-deps` (exit 0).
- pytest run with `-p no:cacheprovider`.

## Commands and results
| Command | Exit | Result |
|---|---|---|
| `python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.lock` | 0 | installed |
| `pytest -p no:cacheprovider -q` (full suite) | 0 | 1020 passed, 1 warning (StarletteDeprecationWarning about httpx in TestClient; not a failure) |
| `pytest tests/integration/test_http_slice1.py` (at HEAD) | 0 | 9 passed |
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 175 files already formatted |
| `mypy src harness tests scripts` | 0 | Success: no issues found in 99 source files |
| `python scripts/validate_governance.py` | 0 | required files: 11; Specs pointer v1.9.12 / 1f6a26d; governance headings, workflow pin, placeholders, secret patterns passed |

## Regression test review
`tests/integration/test_http_slice1.py::test_401_is_not_stored_and_the_same_key_is_evaluated_fresh` (line 77):
- (a) POST to `/v1/accounts/registrations` with no caller context and `Idempotency-Key: k-h1-401` asserts status 401. Covered.
- (b) Asserts `COUNT(*) FROM idempotency_outcomes WHERE idempotency_key = ?` equals 0 after the 401. Covered.
- (c) Same key with valid ADMIN context asserts 201 and `"replayed" not in meta`. Covered.
- (d) Asserts `SELECT outcome_class, http_status FROM idempotency_outcomes WHERE idempotency_key = ?` equals `[("success", 201)]`. Covered.
- The test uses the same sqlite connection as the unit of work (`client` fixture), so the row-count assertions observe the app's writes.

## Mutation check
- Scratch edit, in the worktree only: in `src/abm/main.py`, `register()` 401 branch inserts a `success`/201 row into `idempotency_outcomes` for the denied key, then commits, then returns 401. (The schema's CHECK constraints reject a stored 401, so the mutant stores a valid success row to exercise the assertion.)
- Result: the new test FAILED at line 88 `assert stored == 0` with `assert 1 == 0`. Detection confirmed at assertion (b).
- Reverted with `git checkout -- src/abm/main.py`. `git status --short` was empty. `test_http_slice1.py` re-run at HEAD: 9 passed.

## Work-item accuracy (docs/work-items/TASK-17.md, Remediation section)
- Test name, file, and location ("beside the existing 401 test"): accurate.
- Description (no caller context, no outcome row, then valid context gives fresh 201 with one success outcome): accurate against the test.
- "9 passed" for test_http_slice1.py: confirmed.
- "ruff check . and mypy pass": confirmed.
- "Full-suite run and fresh Tester pass pending": this report supplies the full-suite run (1020 passed). Status line in the work item should be updated by the owner, not by me.
- Claim that the HTTP slice is the right home because the 401 is a transport-layer denial: consistent with `src/abm/main.py` (`unauthorized()` is raised in the route handlers before the application layer).

## Findings
- Blocker: 0
- Major: 0
- Minor (1): The new test covers the non-storage rule only for `POST /v1/accounts/registrations`. The 401 branch is shared by the other command, read, and trace routes (`main.py` `command()`, `history_route()`, `trace_route()`, `account()`), and `test_http_slice2_guards.py::test_every_operation_refuses_missing_caller_context_with_401` checks only the status for every operation. Nothing asserts that a 401 on another command is not stored. TEST-46 ("every command") and the work item's acceptance line 17 are broader than this test. Not a blocker for the TASK-17 Major, which names the 401 gap generally, but the owner may want a parametrized not-stored check over the command routes.
- Observation (1): The work-item Acceptance line for TEST-15 already states 400/403/500/503 are never stored; those are not covered by this test. This is outside the remediation scope.

## Verdict
Verdict: PASS with findings
