# TASK-16 independent Tester report (sanitized record)

**Provenance:** reports of fresh-context Tester and reviewer agents run on 2026-10-10 from the session that built `TASK-16`. Each agent ran read-only and did not build the task. Their output is summarized here; the commands and results are the agents' own.

- Feature commit: `b23e556`. Follow-ups: `1900705` (late-clearing response assertions, Tester M1), `e54c3c0` (mypy type-ignore), `d2670de` (cross-account test), `92dc02f` (refund and restriction tests, DEC-0030 and DEC-0031).
- Merged head: `8827002` (merge of `origin/main` that changed only the Specs pointer files; `git diff --stat 92dc02f 8827002` lists six pointer files, 10 insertions and 10 deletions). PR #27 merged at `ee096fd`.
- Specs: `v1.5.1` / `c1692044221db6a9a64a4943cf5f5d7c99bcf1f3` for the Tester passes; the merged head pins `v1.6.0` / `fa3250e38d04bfc442ee037466a159219092701c`, which changes no card rule.
- Environment: Python 3.12 venv on Windows, `pytest`, `mypy`, `ruff`, and the governance validator, run from the project directory.

## Pass 1: head `e54c3c0` (Tester)

Result: no Blocker. One Major, M-1, then resolved (see below).

| Check | Result |
|---|---|
| `mypy src harness tests scripts` | exit 0, no issues in 54 files |
| `pytest -q` | exit 0, 587 passed |
| `ruff check .` | exit 0 |
| Late-clearing response mutant (response replaced with pre-clearing balances, copy only) | caught: 1 failed (`test_a_late_clearing_after_reversal_posts_one_debit_without_a_hold`, `assert 1000 == 600`) |
| Contract check against `contracts/openapi.yaml` at `v1.5.1` (API-13, API-14, API-15, API-23, API-24) | every stored rejection code the card code can return is declared for its operation |

Coverage, by test name in `tests/integration/test_cards.py` (at that head):
- authorize: `test_authorization_holds_the_funds_and_stores_the_merchant_reference`
- clear: `test_clearing_at_the_authorized_amount_releases_the_hold_and_posts_one_debit`, `test_clearing_may_differ_from_the_authorized_amount_and_create_an_allowed_negative_balance`
- reverse and expire: `test_reversal_releases_the_hold_without_posting`, `test_expiry_releases_the_hold_without_posting`
- late clearing: `test_a_late_clearing_after_reversal_posts_one_debit_without_a_hold`, `test_a_late_clearing_is_accepted_after_closure_and_never_reopens_the_account`
- refund: `test_a_full_refund_after_clearing_posts_one_credit`, `test_a_partial_refund_or_a_refund_before_clearing_is_refused`
- reuse: `test_a_reused_movement_id_is_invalid_transition_and_declared`, `test_a_cleared_movement_cannot_be_cleared_again_or_reversed`
- insufficient funds and restriction: `test_authorization_is_refused_without_funds_or_on_a_blocked_account`

Findings:
- **M-1 (Major):** `refund_card` accepted a refund on a closed account, with no guard and no test. Resolution: JDC decided DEC-0030 (a card refund is a return under INV-16 and is accepted on a closed account). Test added in `92dc02f`: `test_a_card_refund_is_accepted_on_a_closed_account`.
- m-1: the `ACCOUNT_CLOSED` branch of `authorize_card` has no card test. Open (Minor).
- m-2: the closed-account test sets closure with direct SQL, because the closure code is not built yet (TASK-21). Open (Minor).
- m-3: no test for an over-amount refund or a refund from `late_cleared`. Open (Minor).

## Pass 2: head `92dc02f` (Tester, targeted re-check)

Result: no Blocker, no Major.

| Check | Result |
|---|---|
| `mypy src harness tests scripts` | exit 0, no issues in 54 files |
| `pytest -q` | exit 0, 590 passed |
| `ruff check .` | exit 0 |

Mutants, each in a self-contained copy, run against `tests/integration/test_cards.py`:

| Mutant | Result | Killed by |
|---|---|---|
| a. remove the account check in `_card` | 1 failed, 17 passed | `test_a_card_operation_on_another_accounts_movement_is_not_found` |
| b. refund rejects a closed account (`ACCOUNT_CLOSED`) | 1 failed, 17 passed | `test_a_card_refund_is_accepted_on_a_closed_account` |
| c. clearing returns `OUTGOING_BLOCKED` under `outgoing_blocked` | 1 failed, 17 passed | `test_clearing_and_late_clearing_are_not_blocked_by_outgoing_blocked` |

Each mutant was killed only by its targeted test. The three new tests assert outcomes (states, error codes, balances, and counts), not only that a call returns.

The DEC check found DEC-0030 and DEC-0031 on Specs `main` at the time, approved by JDC on 2026-10-10 (option A for both).

Minor findings: the restriction test asserts state only, not the balance or ledger effect of clearing under a restriction; and the closed-account balance `1000` is a funding figure, not derived in the test.

## Review of the merged head `8827002` (fresh-context reviewer, not a Tester pass)

Result: no Blocker, no Major. The reviewer checked the card rules, money and invariant arithmetic, guards before writes, the single transaction, and the stored rejection codes against the contract. It found these test gaps (Minor, not blocking):

- The evidence-reuse guard (`evidence_reference_taken`) is untested in all five operations.
- A refund from `late_cleared`, a second refund, and a second clearing of a `late_cleared` movement are untested.
- The authorization boundary (exactly the available amount, and a second authorization against an existing hold) is untested.
- Authorization on a closed or unknown account is untested.
- The reused-movement-id test compares only part of the counts.
- Rejections in clear, reverse, and refund are not checked for zero side effects.
- Response balances are asserted only for late clearing.

## Not verified

- No final-head Tester pass on `8827002` itself. Pass 2 ran on `92dc02f`; the only later change is the pointer files listed above.
- The Minor items above remain open. They do not block the merged behaviour, but they weaken the tests.
- Production readiness is outside this task.
