# TASK-12, TASK-13, TASK-15 remediation: independent Tester report (sanitized record)

**Provenance:** a fresh-context Tester agent, read-only, run on 2026-10-10 against the merged Code head `b6d9fc0` (merge of PR #37, code commit `43ffbfb`). The agent did not write or fix the code.

**Pinned Specs at the tested revision:** `v1.7.0` / `e6cc2c721ea5207f6488ed1dd645ac770e909f8f` (the pin on `main` at `b6d9fc0`). The v1.7.1 pointer came later in PR #39.

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

## Gate 8: ponytail-review of the remediation diff (`43ffbfb`)

Result: Ship. No Must-fix or Should-fix finding.

- The readiness JSON check is a SELECT only. It writes and repairs nothing. The `elif` skips `integrity_check` only when a malformed row exists, and that path only ever adds `INTEGRITY_FAILED`, so no other reason is lost.
- Scale: readiness now also scans `idempotency_outcomes` once per call. `integrity_check` already scans it, so the cost is the same order.
- Nice to have: the PRAGMA case in `tests/integration/test_readiness.py` has no `try/finally` (test hygiene, scheduled); `_INVALID_JSON` could be inlined.

## Not verified

- TASK-16: its final-head Tester pass is still open, and JDC decides its status.
- Production readiness and any backup or restore claim are outside this record.
