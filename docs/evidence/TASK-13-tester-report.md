# TASK-13 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only, did not build the task. The Tester worked in a detached worktree at the verified merge commit, edited nothing in the main checkout, and removed the worktree after the run. Mutants were applied only to a separate scratch copy.

## Revision verified

- Merge commit: `487be1f62e9746ba0cdfcabd320bc8983fcc7943` (full SHA), PR #17 `task-13-incoming-ach`, merged on `main`.
- Work item: `docs/work-items/TASK-13.md` at that commit (Status: Implemented).
- Specs pin in the code repo: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91` (`SPEC_VERSION`).
- HEAD confirmed as `487be1f62e9746ba0cdfcabd320bc8983fcc7943`; worktree clean before gates.

## Environment

- Windows 11 Home 10.0.26300; Git Bash for shell commands.
- Python 3.12.10 from the project venv (`.venv\Scripts\python.exe`), run from the detached worktree; `-p no:cacheprovider` on pytest.
- Specs read from the Specs repo at the pinned commit (`git show`), plus later `main` for the Specs PR #5 comparison.

## Result

PASS with findings. Blocker 0, Major 2, Minor 5. All gates pass and all 19 focused tests pass; both Majors are a traceability gap and a test gap, not a defect in the current behaviour.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| (1) HEAD | PASS | `git rev-parse HEAD` = `487be1f62e9746ba0cdfcabd320bc8983fcc7943`; worktree clean. |
| (2a) `mypy src harness tests scripts` | PASS | exit 0; "Success: no issues found in 47 source files". |
| (2b) `pytest -q -p no:cacheprovider` | PASS | exit 0; 527 passed in about 152 s. (Work item records 523 at its time; the head count is 527.) |
| (2c) `ruff check .` | PASS | exit 0; "All checks passed!". |
| (2d) `ruff format --check .` | PASS | exit 0; "74 files already formatted". |
| (2e) `scripts/validate_governance.py` | PASS | exit 0; "TASK-01 VALIDATION PASSED"; Specs pointer v1.0.1 / 5d1cd41. |
| (3a) Work item acceptance: notice creates pending movement, no ledger row, no balance change | PASS | `test_notice_creates_a_pending_movement_with_no_balance_effect`. Code: `create_incoming_ach` never calls `apply_balance`. |
| (3b) Settlement posts one credit, settles, records evidence and trace | PASS | `test_settlement_posts_one_credit_and_settles_the_movement`; `test_settlement_records_its_trace_entry...`. |
| (3c) Return posts one full debit and returns the movement | PASS | `test_return_posts_one_full_debit_and_returns_the_movement`. |
| (3d) Same key/request replays with no second effect; changed request conflicts | PASS | `test_same_key_and_request_replays...`; `test_same_key_with_a_changed_request...`. |
| (3e) Second settlement and second return refused as INVALID_TRANSITION | PASS | `test_a_second_settlement...`; `test_a_second_return_is_refused`. |
| (3f) Evidence reference reuse refused; return before settlement refused; amount mismatch refused | PASS | `test_an_evidence_reference_cannot_be_reused...`; `test_a_return_before_settlement...`; `test_a_return_that_differs...` (AMOUNT_MISMATCH). |
| (3g) Unknown movement/account not found; caller without role refused before storage | PASS | `test_an_unknown_movement_or_account...`; `test_a_caller_without_the_role...` (storage object raises if touched). |
| (3h) Closed account takes no new notice; settle refused, return accepted | PASS | `test_a_closed_account_takes_no_new_incoming_movement` (ACCOUNT_CLOSED); parametrised `test_a_closed_account_refuses_settlement_but_accepts_its_return`. |
| (3i) Invalid amounts refused with nothing stored | PASS | parametrised test: 0, -1, over-bound, 1.5, "500", True, None. |
| (3j) Storage fault mid-settlement rolls back every effect | PASS | `test_a_storage_fault_mid_settlement...` fails `apply_balance`; counts and balance unchanged. |
| (3k) Reopen after full lifecycle is ready; trace accepted | PASS | `test_the_database_is_ready_after_a_full_lifecycle_and_a_restart`; `readiness.py` line 38 checks projection equals ledger sum, so the projection criterion is covered via `readiness_reasons() == []`. |
| (3l) Specs links: specs/02 incoming ACH; specs/04 API-04..API-06 | PASS with finding | Pinned v1.0.1 does not contain the closed-account and duplicate-movement rules; see Finding F1. |
| (4a) Notice creates pending, no balance change | PASS | Covered by test and by mutant M1 (caught). |
| (4b) Settlement credits exactly once | PASS | Mutant M2 (no pending check) and M3 (no credit) both caught. |
| (4c) Second settlement refused | PASS | Mutant M2 caught by `test_a_second_settlement...`. |
| (4d) Return after settlement only, one full return | PASS | Mutants M4 (return from pending) and M5 (amount unchecked) caught. |
| (4e) Closed account rejects new notices | PASS | Mutant M6 caught. |

Mutants were applied one at a time to a scratch copy (src, tests, harness, migrations, pyproject.toml) with pytest run inside the copy on `tests/integration/test_incoming_ach.py` (26 tests; baseline 26 passed in the copy).

## Mutant results

| ID | Mutant (in `src/abm/application/incoming_ach.py`) | Result | Caught by |
|---|---|---|---|
| M1 | Notice applies the amount to the balance | CAUGHT | 9 failures, incl. no-balance-effect test |
| M2 | Settlement skips the pending-state check | CAUGHT | `test_a_second_settlement_is_refused...` |
| M3 | Settlement does not apply the credit to the balance | CAUGHT | 8 failures, incl. settlement and return tests |
| M4 | Return allowed from pending | CAUGHT | `test_a_return_before_settlement_is_refused` |
| M5 | Return amount not compared with settled amount | CAUGHT | `test_a_return_that_differs...` |
| M6 | Notice allowed on closed account | CAUGHT | `test_a_closed_account_takes_no_new_incoming_movement` |
| M7 | Settlement allowed on closed account | CAUGHT | parametrised closed-account test (settle) |
| M8 | Return refused on closed account | CAUGHT | parametrised closed-account test (return) |
| M9 | Settlement does not bind movement to its account | SURVIVED | none; see F2 |
| M10 | Settlement evidence-reuse check removed | CAUGHT | `test_an_evidence_reference_cannot_be_reused...` |
| M11 | Return posted as credit | CAUGHT | 4 failures |
| M12 | Return does not set state to returned | CAUGHT | `test_a_second_return_is_refused` |
| M13 | Settlement does not set state to settled | CAUGHT | 6 failures |
| M14 | Return evidence-reuse check removed | SURVIVED | none; see F3 |

Result: 12 of 14 caught; 2 survived (M9, M14). Probe for M14 in the scratch copy: a reused return evidence reference returns `INVALID_TRANSITION` with the check present, and `INTERNAL_ERROR` (500) with it removed. The schema primary key on `movement_evidence.evidence_reference` is the only backstop.

## Findings

Ranked by severity.

**Major**

- **F1 (Major, traceability).** The code pins Specs `v1.0.1` (`5d1cd41`), but the closed-account and duplicate-movement rules it implements come from Specs PR #5 (merged to Specs `main` as `47a50c2`) and DEC-0026, which are not in the pinned text. At `5d1cd41`: no DEC-0026; API-06 is not in the late-evidence list; no "API-05 refused with ACCOUNT_CLOSED" sentence. The work item still says PR #5 is "awaiting approval", and its Implementation notes say a return on a closed account is refused, which contradicts the code and tests. Action: pin a Specs version that contains PR #5, or record the approval; correct the work item.
- **F2 (Major, test gap).** No test covers a movement belonging to a different account. Mutant M9 (dropping `record.account_id != target` in settlement) passes all 26 tests. Without the check, a settlement through account A could credit account A for a movement that belongs to account B. The return path has the same check, also untested. Action: add cross-account tests for settlement and return.

**Minor**

- **F3 (Minor).** Return-side evidence reuse is untested. Mutant M14 survives; the response changes from `INVALID_TRANSITION` to a 500 `INTERNAL_ERROR`, and nothing detects it.
- **F4 (Minor).** The work item's Implementation notes (closed-account settlement and return refused) conflict with its Completion section and with the code (return accepted on closed account). Also the test count (523) and PR status are stale relative to head (527).
- **F5 (Minor).** INV-10 negative-balance return path is not exercised (acknowledged in the work item; needs an outgoing debit from TASK-14).
- **F6 (Minor, Specs-side, outside this code repo).** Specs `main` `specs/04-api.md` line 84 contains a garbled sentence: "API-06, Any operation that creates a record from a caller-supplied `movement_id`…". It came from merging PR #5 and DEC-0026 text; the leading "API-06," is orphaned.
- **F7 (Minor, carried over).** A credit beyond the schema's cents bound becomes `INTERNAL_ERROR` (already recorded in the work item as not fixed). Not reproduced here.

## Not verified

- The Ponytail review and any non-Tester checks were not run; this report is the Tester's own result.
- Concurrency and cross-process behaviour (TASK-18) were not tested, as the work item excludes them.
- The HTTP envelopes (API-04..06 routes, TASK-25) were not exercised; this is a service-layer check only.
- Negative-balance return (INV-10) was not exercised.
- CI results on the PR were not inspected; only local gates were run on the merge commit.
- Specs `main` is at v1.6.0; only the pinned v1.0.1 text and the PR #5 diff were compared, not the whole later Specs set.
- Mutant copy used CRLF line endings from my scratch write; logic was identical to the worktree file (verified with a diff ignoring carriage returns).
