# TASK-36 Tester report (merged revision)

**Task:** TASK-36 container HTTP smoke check. **Merged commit:** bf965d8 (PR #108). **PR head:** 7559519. **Specs pin:** v1.9.12 / 1f6a26d; Specs main 857092a. **Date:** 2026-10-11. **Role:** fresh-context Tester, read-only.

## Gates on bf965d8

| Gate | Result |
|---|---|
| pytest | `989 passed, 1 warning in 187.76s` (exit 0) |
| ruff check . | passed (exit 0) |
| ruff format --check . | 159 files already formatted (exit 0) |
| mypy src harness tests scripts | exit 0 (92 files) |
| validate_governance.py | exit 0 |
| validate_toolchain.py | exit 0 |

## Scope

| Probe | Evidence | Result |
|---|---|---|
| Liveness and readiness | scripts/smoke_container.py, 200 each | Pass |
| Registration | 201, contract match | Pass |
| Authorized account read (exact scope) | 200, account_id checked | Pass |
| Money-changing instruction (incoming ACH notice then settlement) | 201 then 200; history one credit of 100; balance 100 | Pass |
| Denied requests | 401 UNAUTHORIZED with no context; 403 for a payment role registration; 404 for the denied account; balance unchanged | Pass |
| Documented fields only; no new route | Diff of src/ since 01b2cf5 is empty | Pass |
| CI evidence | Run 38165041466, container-check on 7559519: "SMOKE CHECK PASSED" | Pass |

## Mutants (scratch copy of bf965d8, probe tests)

| Mutant | Result |
|---|---|
| m1: denied-balance check removed | survived (tests do not exercise state-change failure paths) |
| m2: denied registration expected 403 changed to 200 | killed |
| m3: denied read expected 401 changed to 200 | killed |
| m4: denied-account 404 check removed | survived (same gap) |

## Findings

| ID | Class | Status |
|---|---|---|
| F1 | Minor | README did not name the smoke step (work-item acceptance). Fixed in the close-out PR. |
| F2 | Minor | State-change failure paths not exercised by a test. Scheduled (work item). |
| F3 | Note | History credit check matches amount only, not direction or effect kind. Scheduled (work item). |

## Verdict

**PASS** for TASK-36 at bf965d8. No Blocker or Major.

## Not verified

The container was run only in CI (run 38165041466). Probe bodies can drift from the contract without a local check; only a Specs change or the conformance job would catch that.
