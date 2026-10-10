# TASK-12, TASK-13, TASK-15 remediation: independent Tester report (sanitized record)

**Provenance:** a fresh-context Tester agent, read-only, run on 2026-10-10 against the merged Code head `b6d9fc0` (merge of PR #37, code commit `43ffbfb`). The agent did not write or fix the code.

**Pinned Specs:** `v1.7.1` / `8c47d24c34e922154a9f5b481c32d46375b32721` (validator reported `v1.7.0` at that revision, the pin before PR #39).

## Gates (venv python, `-I`)

| Gate | Result |
|---|---|
| `mypy src harness tests scripts` | exit 0, "no issues found in 54 source files" |
| `pytest -q -p no:cacheprovider` | exit 0, 593 passed |
| `ruff check .` | exit 0 |
| `ruff format --check .` | exit 0, 93 files formatted |
| `scripts/validate_governance.py` | exit 0, all checks passed |

## Claims, each test run alone

| Claim | Test | Result |
|---|---|---|
| A malformed stored idempotency response is INTEGRITY_FAILED (TASK-12) | `test_direct_corruption_makes_readiness_fail_with_a_safe_code[stored idempotency response that is not valid JSON]` | PASS, expects `[INTEGRITY_FAILED]` |
| Another account's movement is MOVEMENT_NOT_FOUND for settlement and return, with no write (TASK-13 F2) | `test_another_accounts_movement_is_not_found_for_settlement_or_return` | PASS |
| A closed source account takes no transfer and writes nothing (TASK-15) | `test_a_closed_source_account_takes_no_transfer_and_nothing_is_written` | PASS |

## Mutation checks (one mutant per copy of the worktree)

| Mutant | Result |
|---|---|
| readiness JSON check disabled (`if False:`) | FAILS: `['DATABASE_UNAVAILABLE']` instead of `['INTEGRITY_FAILED']` |
| incoming ACH settlement owner check removed | FAILS: wrong-account settlement returned Success |
| transfer source status check reduced to destination only | FAILS: transfer from a closed source completed |

## Findings

- Blocker: none. Major: none open on `b6d9fc0`.
- Minors scheduled, not resolved here (see the work items): the PRAGMA cleanup in the new readiness case (test hygiene only); the unsupported-schema readiness test (TASK-12, trigger TASK-25); the TASK-16 Minors (TASK-17) and `finalize_hold` rowcount check (TASK-18).
- TASK-13 F1 (traceability) is not re-verified by this pass. It is resolved only by reference in the work item, so TASK-13 stays Implemented.

## Not verified

- TASK-16: its final-head Tester pass is still open, and JDC decides its status.
- Production readiness and any backup or restore claim are outside this record.
