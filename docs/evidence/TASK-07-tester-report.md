# TASK-07 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only, did not build the task. The Tester worked in a detached worktree of the merge commit, made no edits or commits in the main checkout, changed no git config, pushed nothing, and created no refs.

## Revision verified

- Merge commit: `5eab23f19bb0494efb1b17a96931bbf7541bdc0b` (PR #13, `task-07-connection-transactions`, merged to `main`)
- Second parent: `4dee0689063b64c4df80d939b69951a51e2a12c2`
- Work item: `docs/work-items/TASK-07.md` at that commit (Specs `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`)

## Environment

- Windows 11 Home 10.0.26300, Git Bash and PowerShell
- Python 3.12.10 from the project venv (`.venv`), run from the Tester worktree
- pytest run with `-p no:cacheprovider`
- Mutation copy: `src`, `tests`, `harness`, `migrations`, `pyproject.toml` copied to a scratch directory; `pytest` run from inside it; `abm` resolved only from the copy (`pythonpath = ["src", "."]`)

## Result

PASS with findings. Blocker 0, Major 0, Minor 2.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| HEAD confirmed | PASS | `git rev-parse HEAD` in the worktree = `5eab23f19bb0494efb1b17a96931bbf7541bdc0b`; parents `54c9ebe` and `4dee068`; subject "Merge pull request #13 from juandcn9/task-07-connection-transactions" |
| `mypy src harness tests scripts` | PASS | exit 0, "Success: no issues found in 36 source files" (foreground re-run confirmed) |
| `pytest -q` | PASS | exit 0, 420 passed in 132.79s (full suite at the merge commit) |
| `ruff check .` | PASS | exit 0, "All checks passed!" |
| `ruff format --check .` | PASS | exit 0, "59 files already formatted" |
| `scripts/validate_governance.py` | PASS | exit 0, "TASK-01 VALIDATION PASSED"; Specs pointer `v1.0.1 / 5d1cd410399a6fb0154a0117728c409cc7f2ec91`, matching README.md |
| Focused tests `tests/integration/test_database.py` | PASS | 32 passed (real SQLite files) |
| Acceptance: pragmas read back, autocommit, FK enforced, busy-timeout bounds, unopenable path message without path | PASS | Covered by tests `test_required_settings_are_applied_and_verified`, `test_foreign_keys_are_enforced`, `test_busy_timeout_must_be_a_bounded_integer`, `test_unopenable_path_fails_without_leaking_it`, `test_every_valid_busy_timeout_is_applied_exactly` (all 1..60000) |
| Acceptance: commit atomic, failure after every step leaves no effect, constraint/KeyboardInterrupt/BaseException roll back | PASS | `test_commit_makes_every_step_visible_together`, `test_failure_after_every_step_leaves_all_effects_or_none`, `test_constraint_failure_inside_a_step_rolls_everything_back`, `test_baseexception_also_rolls_back` |
| Acceptance: second writer refused with retryable SERVICE_BUSY, no partial row; writers serialized; wait-then-see-commit | PASS | `test_second_writer_is_refused_with_a_safe_retryable_busy_failure`, `test_writers_are_serialized_not_interleaved`, `test_second_writer_waits_for_the_first_and_then_sees_its_commit` |
| Acceptance: read snapshot consistent while another connection commits | PASS | `test_read_transaction_sees_one_consistent_snapshot` |
| Acceptance: disk-full (max_page_count) gives SERVICE_UNREADY, no partial rows | PASS | `test_disk_full_is_a_safe_failure_with_no_partial_effect` (simulated, not a real full volume) |
| Acceptance: every mapped SQLite code has its own test; driver text never exposed | PASS | `test_each_sqlite_code_maps_to_its_safe_failure` (parametrized), `test_error_mapping_never_exposes_driver_text` |
| Code review of `database.py` against rules | PASS | `BEGIN IMMEDIATE` in `write_transaction` before the body; ROLLBACK on any `BaseException` when still in a transaction; COMMIT failure is inside the try and rolls back; `read_transaction` uses deferred BEGIN with rollback in finally; `to_failure` uses `sqlite_errorcode & 0xFF`; failure messages are fixed text; a failed configuration step closes the connection |
| Work item claim "removing the rollback makes three tests fail" | PASS | Mutant M2 below fails exactly three tests |

## Mutants (self-contained copy, `pytest tests/integration/test_database.py` run from inside the copy)

Baseline in the copy: 32 passed.

| Mutant | Change | Result | Caught by |
|---|---|---|---|
| M1 deferred begin | `BEGIN IMMEDIATE` changed to `BEGIN` in `write_transaction` | Caught (2 failed) | `test_second_writer_is_refused_with_a_safe_retryable_busy_failure`, `test_second_writer_waits_for_the_first_and_then_sees_its_commit` |
| M2 no rollback | `ROLLBACK` replaced by `COMMIT` on the exception path | Caught (3 failed) | `test_failure_after_every_step_leaves_all_effects_or_none`, `test_constraint_failure_inside_a_step_rolls_everything_back`, `test_baseexception_also_rolls_back` |
| M3 busy mapped as unready | busy/locked branch removed from `to_failure` | Caught (4 failed) | busy-refusal test and the parametrized codes 5, 6, 517 |
| M4 no synchronous FULL | `PRAGMA synchronous = FULL` removed from `open_database` | Survived (32 passed) | Not caught. Equivalent on this build: the default synchronous level is FULL, so the read-back check still passes. See Finding 2. |
| M5 driver text leak | generic INTERNAL_ERROR message replaced by `str(exc)` | Caught (1 failed) | `test_error_mapping_never_exposes_driver_text` |

The copy was restored to the original after the run (content identical to the committed file apart from line endings). Only the scratch copy was mutated.

## Findings

1. Minor. Work item test count is stale. `docs/work-items/TASK-07.md` says "pytest 337 passed in this branch". At the verified merge commit the full suite gives 420 passed. The count should be updated in a documentation-only change. No behavior impact.
2. Minor. The `synchronous = FULL` setting is not discriminated by the tests. Removing the PRAGMA (M4) leaves all 32 tests green, because the SQLite default on this build is already FULL, so the read-back check passes either way. The read-back still protects against a non-FULL default build (it would raise `DatabaseUnavailable`), so the risk is low. Either accept it as a documented equivalence, or add a test that sets a different default and proves the PRAGMA is applied.

No Blocker or Major findings.

## Not verified

- Real disk-full or kill -9 / multi-process crash recovery (deferred to TASK-28, as the work item states).
- Pinned CI Python 3.12.15 and CI workflow runs; only the local venv (Python 3.12.10) was used.
- Behavior of `SQLITE_BUSY` raised during an already-open write transaction (checkpoint); acknowledged as a residual risk in the work item and not tested here.
- Nested transaction misuse and a body that commits on its own (recorded as unchanged misuse cases in the work item; no tests).
- Behavior under the `ABM_BUSY_TIMEOUT_MS` setting (not parsed yet; TASK-12/TASK-26).
- The GitHub PR #13 check status and the review record; only the local merge commit was verified.
