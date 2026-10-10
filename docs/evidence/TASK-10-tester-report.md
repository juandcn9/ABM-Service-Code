# TASK-10 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only, did not build the task. The run used a detached worktree at the merge commit, made no commits, pushes, refs, or config changes in the main checkout, and removed its worktree afterward.

Revision verified: merge commit `17ffbcfc1cfbd5d4ce4cbf3247cd5c7f9eeb5ea1` (PR #14, `task-10-registration`, merged to `main`). HEAD of the detached worktree confirmed equal to this SHA. Work item: `docs/work-items/TASK-10.md` at that commit. Specs pin: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91` (commit exists in the Specs repo; the Specs repo HEAD was a later commit, not used as the pin).

Environment: Windows 11 Home 10.0.26300; Python 3.12.10 from the repo `.venv` (`C:\Users\juand\OneDrive\EFEX\ABM-Service-Code\.venv\Scripts\python.exe`); pytest run with `-p no:cacheprovider`; mutants run in a separate copy of `src`, `tests`, `harness`, `migrations`, `pyproject.toml`. Other agents' pytest processes were active on the machine during the run; they did not touch this worktree's results.

## Result

PASS with findings (Blocker 0, Major 0, Minor 3).

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| HEAD confirmed | PASS | Detached worktree HEAD = `17ffbcfc1cfbd5d4ce4cbf3247cd5c7f9eeb5ea1`, clean status. |
| `mypy src harness tests scripts` | PASS (exit 0) | "Success: no issues found in 41 source files". |
| `pytest -q` | PASS (exit 0) | 434 passed in 106.57s. |
| `ruff check .` | PASS (exit 0) | "All checks passed!". |
| `ruff format --check .` | PASS (exit 0) | "65 files already formatted". |
| `scripts/validate_governance.py` | PASS (exit 0) | TASK-01 VALIDATION PASSED; Specs pointer v1.0.1 / 5d1cd41; headings, workflow pin, placeholders, secret patterns passed. |
| Work item traceability | PASS | Pinned Specs SHA exists; cited IDs (BT-09, FR-15, INV-02/03/06/17, API-01, DATA-01/05/06/07, TEST-01/15/16, DEC-0011/0012) resolve in Specs. `DEC-0011` text matches the implemented storable set (404, non-conflict 409, 422; not 400/401/403/IDEMPOTENCY_CONFLICT/500/503). `specs/04` API-01 `x-replay-result` matches the code's replay behavior (201 success, 409 DUPLICATE_ACCOUNT replayed; changed fingerprint = unstored IDEMPOTENCY_CONFLICT). |
| Same key + same fingerprint replays stored outcome exactly | PASS | `test_same_key_and_request_replays_the_original_outcome_without_new_rows` (clock advanced 3600s; `replayed` true; no new rows); `test_a_stored_rejection_replays_exactly`. Code: `_replay` reads the stored body. |
| Same key + different fingerprint = IDEMPOTENCY_CONFLICT, no write | PASS | `test_changed_request_under_the_same_key_conflicts_and_stores_nothing` covers eligibility_reference, account_id, instruction_id changes; table counts unchanged; original replays afterwards. Conflict path returns before `save_outcome`. |
| Storable rejection stored and replayed | PASS | `test_duplicate_account_or_customer_is_rejected_without_extra_business_rows` (two outcome rows, 409 deterministic_rejection); `test_a_stored_rejection_replays_exactly`. |
| Non-storable error not stored | PASS | `test_transient_failure_is_rolled_back_and_not_stored` (SERVICE_BUSY from work; account and outcome both absent). `_to_outcome` returns None for codes outside `STORABLE_REJECTIONS`; the abort path rolls back. |
| Duplicate registration refused without second row | PASS | Account-or-customer duplicate check; `test_concurrent_registrations_of_one_customer_create_exactly_one_account` (6 threads: 1 Success, 5 DUPLICATE_ACCOUNT, 1 account, 1 trace). |
| Auth before storage | PASS | `test_unauthorized_caller_never_reaches_storage` (Forbidden UoW raises if touched). |
| Validation before storage | PASS | `test_invalid_requests_are_not_stored_and_have_no_effect` (12 bad bodies, 6 bad keys; all counts zero). |
| Fault injection before each of the 5 storage calls | PASS | `test_failure_after_every_persistence_step_leaves_all_effects_or_none`; then the same request succeeds. |
| Busy database | PASS | `test_busy_database_gives_a_retryable_failure_and_stores_nothing` (SERVICE_BUSY, retryable, nothing stored). |
| Clock failure | PASS | `test_clock_failure_rejects_the_instruction_without_effect` (SERVICE_UNREADY, no rows). |
| Scope key deterministic, 64-hex, pair-unambiguous | PASS | `test_scope_keys_are_deterministic_and_fit_the_stored_alphabet`. |
| Mutation (independent) | PASS | 9 of 9 mutants caught; see table. |

## Mutants

Each mutant was applied to a copy of the repo (only `src` changed) and `tests/integration/test_registration.py` was run from inside the copy.

| # | Mutant | Result | Evidence |
|---|---|---|---|
| M1 | Fingerprint comparison disabled (`if False:`) | Caught | exit 1, 1 failed / 13 passed |
| M2 | Non-storable failures stored as 422 outcome | Caught | exit 1, 1 failed / 13 passed |
| M3 | Duplicate account/customer check removed | Caught | exit 1, 5 failed / 9 passed |
| M4 | Replay reported as `replayed=False` | Caught | exit 1, 2 failed / 12 passed |
| M5 | Conflict returns the stored outcome instead of IDEMPOTENCY_CONFLICT | Caught | exit 1, 1 failed / 13 passed |
| M6 | Retention row not created (SELECT ... WHERE 0) | Caught | exit 1, 1 failed / 13 passed |
| M7 | Deterministic rejections not stored (save only on Success) | Caught | exit 1, 2 failed / 12 passed |
| M8 | Scope key ignores operation | Caught | exit 1, 1 failed / 13 passed |
| M9 | Deferred `BEGIN` instead of `BEGIN IMMEDIATE` | Caught | exit 1, 2 failed / 12 passed |

## Findings

Ranked. None is a Blocker or Major. All three are either deferred by the work item's explicit exclusions or are residual risks it already records.

1. **Minor. Safe rejected-request security evidence not emitted for deterministic rejections.** `specs/04` API-01 `x-audit-security-evidence` says a deterministic 404/non-conflict-409/422 stores the idempotency outcome plus safe rejected-request security evidence. `DUPLICATE_ACCOUNT` is a stored deterministic rejection, and no evidence row or log is written. The work item excludes this (TASK-23, TASK-26), so it is a scheduled gap, not a regression. Recommend the TASK-23 review confirm the scheduled coverage.
2. **Minor. Unexpected exceptions from the instruction propagate out of `run_idempotent`.** The transaction is rolled back, but the exception is not mapped to a safe `INTERNAL_ERROR`. The work item carries this to TASK-25 (API edge). `test_failure_after_every_persistence_step...` asserts the raw `RuntimeError` propagates, so the current test suite pins this behavior; it must change when TASK-25 lands.
3. **Minor. "Failure only before writes" is convention, not enforced, for storable rejections.** If a future `work` returns a storable rejection after a partial write, that write is committed together with the stored outcome. The work item records this as a residual risk and suggests a savepoint in a later task. Verified by reading the code, not by a test.

Observations that are not defects: the fingerprint includes `instruction_id` (the work item flags this as a Specs question before TASK-13); the scope is hashed rather than `customer_id + registration` (flagged for the Specs Updater); the scope label uses `register_account` rather than `registration`. These are recorded in the work item and do not change the verdict.

## Not verified

- No real process restart replay (deferred to TASK-28).
- No HTTP edge, headers, or envelope (TASK-25) and no security evidence rows (TASK-23).
- Concurrency test ran once; no repeated or stress runs.
- Specs repo was read at the pinned SHA only for the cited lines (DEC-0011/0012, scope wording, API-01 x-replay and x-audit fields); the full Specs documents and the newer Specs HEAD were not audited.
- Gate `ponytail-review` and the Builder's own review were not re-run (Tester scope).
