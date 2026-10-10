# TASK-16 independent Tester report, re-verification after PR 43 (second record file)

**Provenance:** fresh-context Tester agents, read-only, run on 2026-10-10. Pass 3 is the re-verification after the single Major below was closed.

## Pass 3a: Code head `377de0e` (FAIL)

| Check | Result |
|---|---|
| Gates (mypy, pytest 600, ruff check and format, validate_governance) | all pass |
| Mutation: `if False:` at the clear_card evidence-reuse check | survived: no test failed |
| Mutations: ACCOUNT_CLOSED, INSUFFICIENT_FUNDS, refund AMOUNT_MISMATCH | killed |

Verdict: **FAIL**, one Major: no test covers a clearing that reuses an evidence reference. A suspicion that the reuse surfaces as an `IntegrityError` (`INTERNAL_ERROR`) was checked and is wrong: the probe returns `INVALID_TRANSITION` when the idempotency key is distinct.

## Pass 3b: the fix (PR #43, merged as `0ce8071`)

- Test only: `test_a_clearing_that_reuses_an_evidence_reference_is_refused_and_writes_nothing` in `tests/integration/test_cards.py`. Asserts `INVALID_TRANSITION`, that the second movement stays `authorized_with_hold`, and that counts and balances are unchanged. No code change.
- Reviewed clean (fresh-context review at head `53056c5`, no open Blocker or Major). Approved by JDC at `53056c5`.

## Pass 3c: merged head `0ce8071` (PASS)

| Gate | Result |
|---|---|
| `mypy src harness tests scripts` | exit 0, 54 files |
| `pytest -q -p no:cacheprovider` | exit 0, 601 passed |
| `ruff check .`, `ruff format --check .` | exit 0 |
| `scripts/validate_governance.py` | exit 0, pin Specs `v1.8.0` / `e4d97ff294dbc0d6d94e88991b65f59badebd6fc` |
| `tests/integration/test_cards.py` | 25 passed |

Mutants, each in its own copy:

| Mutant | Result | Killing test |
|---|---|---|
| ACCOUNT_CLOSED dead in `authorize_card` | killed (1 failed) | `test_authorization_on_a_closed_account_is_refused_and_writes_nothing` |
| INSUFFICIENT_FUNDS dead in `authorize_card` | killed (1 failed) | `test_authorization_is_refused_without_funds_or_on_a_blocked_account` |
| refund AMOUNT_MISMATCH always passes | killed (2 failed) | `test_a_partial_refund_or_a_refund_before_clearing_is_refused`; `test_a_refund_that_differs_from_the_clearing_is_refused_and_writes_nothing` |
| clear evidence-reuse check dead | killed (1 failed) | `test_a_clearing_that_reuses_an_evidence_reference_is_refused_and_writes_nothing` |

Verdict: **PASS** for TASK-16 at `0ce8071`: no open Blocker or Major.

## Not verified

- The Minors listed in PR #41 remain open and scheduled (for example the refund from `late_cleared`, zero-side-effect checks on rejected clear and reverse, the authorization boundary, and card fingerprint tests). They are not blocking this verdict.
- The closed-account card cases that close an account by direct SQL stay with TASK-21 (closure).
- Status: **Verified** (JDC decision, recorded as DEC-0038 in Specs). This record is the evidence for it.
