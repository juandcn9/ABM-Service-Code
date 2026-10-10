# TASK-14 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only with respect to the Code repo (no edits, commits, config changes, pushes, or refs). The Tester did not build TASK-14. Verification ran in a detached worktree at the merge commit, which was removed afterwards without force. Mutants were made in a separate copy of `src`, `tests`, `harness`, `migrations`, and `pyproject.toml`.

Revision verified: merge commit `a893cc39ca0ee1f971e7664a5702d16267a60d9f` (PR #22, `task-14-outgoing-ach`, merged on `main`). HEAD confirmed equal to this SHA.

Environment: Windows 11 Home 10.0.26300; repo venv Python 3.12.10 (`.venv` of the main checkout, used from the worktree); pytest run with `-p no:cacheprovider`. Specs pin read from `SPEC_VERSION`: v1.2.0 / `32befdaa710404145fa2c13128a8015da761d1f5`.

## Result

PASS with findings. Blocker 0, Major 1, Minor 4.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| HEAD confirmed | PASS | `git rev-parse HEAD` = `a893cc39ca0ee1f971e7664a5702d16267a60d9f`, subject "Merge pull request #22 from juandcn9/task-14-outgoing-ach". |
| `mypy src harness tests scripts` | PASS (exit 0) | "Success: no issues found in 50 source files". |
| `pytest -q` | PASS (exit 0) | 561 passed on a clean re-run (116.85 s); 561 collected. |
| `ruff check .` | PASS (exit 0) | "All checks passed!". |
| `ruff format --check .` | PASS (exit 0) | 78 files already formatted. |
| `scripts/validate_governance.py` | PASS (exit 0) | "TASK-01 VALIDATION PASSED"; Specs pointer v1.2.0 / 32befdaa. |
| Acceptance evidence (work item) | PASS | `tests/integration/test_outgoing_ach.py` (18 tests) passes against real SQLite: one active hold kept with balance; insufficient funds stores only the outcome; hold reduces available funds; closed and blocked refusals; duplicate id; submit keeps hold; settle debits once and posts hold; settle before submit refused; reject and cancel release without debit; cancel after submit refused; one full return; amount mismatch; replay creates no second hold; injected fault rolls back; restart is ready; reserved settlement may go negative (DEC-0024). |
| Hold rule attacks (Tester-written, 13 checks, copy only) | PASS | Create reports available = current minus hold (1000/400/600). Settle twice refused, one debit. Reject or cancel after settle refused. Reject before submit refused. Each terminal path leaves its hold exactly once (released, released, posted). Return twice refused, one credit. Return after rejection refused. Duplicate movement id: INVALID_TRANSITION, no business-table change. ACCOUNT_CLOSED and OUTGOING_BLOCKED: no business-table change. Reused evidence refused with no write. Readiness after reject and cancel stays ready. |
| Declared codes vs pinned contract (v1.2.0 SHA) | PASS for submit, settle, reject, cancel, return; FINDING for create | Submit, settle, reject, cancel declare 404 ACCOUNT_NOT_FOUND/MOVEMENT_NOT_FOUND and 409 INVALID_TRANSITION. Return also declares 422 AMOUNT_MISMATCH. Create declares 404 ACCOUNT_NOT_FOUND and 422 ACCOUNT_CLOSED/INSUFFICIENT_FUNDS/OUTGOING_BLOCKED only, with no 409 INVALID_TRANSITION at the pinned SHA (see Finding 1). |
| Authority trace for DEC-0023 and DEC-0024 at the pinned SHA | FAIL (Major) | At `32befdaa`: INV-10 lacks the outgoing-settlement clause; DEC-0023 and DEC-0024 are absent from `governance/decisions.md`. Their Specs commit `828b351` is a descendant of the pin. |

## Mutant results

All mutants were applied to a copy of `src/abm/application/outgoing_ach.py`. Each was run against `tests/integration/test_outgoing_ach.py` plus the Tester attack file. The unmutated copy passes 31 of 31.

| Mutant | Description | Caught | Evidence |
|---|---|---|---|
| M1 | Settlement does not finalize the hold (`finalize_hold` disabled). | Yes | 12 failed (7 existing, 5 attack). |
| M2 | Submission finalizes the hold (`closes_hold=True` on submit). | Yes | 13 failed. |
| M3 | Return allows a second return (state guard accepts `returned`). | Yes, by accident | 1 failed (`test_return_twice_credits_once`). It fails with `INTERNAL_ERROR`, not `INVALID_TRANSITION`: the duplicate ledger primary key is the backstop, not the state guard. |
| M4 | Settle, reject, and cancel skip the active-hold check. | Yes | 1 failed (`test_a_closing_transition_without_an_active_hold_moves_no_money`). |
| M5 | Create skips the ACCOUNT_CLOSED check. | Yes | 2 failed (existing restricted/closed test and attack closed test). |
| M6 | Available balance ignores holds on create. | Yes | 1 failed (`test_an_existing_hold_reduces_the_funds_available_to_a_new_acceptance`). |

## Findings

Ranked. Counts: Blocker 0, Major 1, Minor 4.

1. **Major: The pinned Specs version does not contain the authority cited for two behaviors.** TASK-14 cites Specs v1.2.0 / `32befdaa`, which is the pin in `SPEC_VERSION`. The work item and the code rely on DEC-0023 (duplicate outgoing movement id is `INVALID_TRANSITION`, declared on API-07) and DEC-0024 (INV-10 extended for settlement of a reserved outgoing movement). Both are recorded in Specs commit `828b351` (Specs PR #11), which is not an ancestor of `32befdaa`. At the pinned SHA, API-07 declares no 409 `INVALID_TRANSITION`, and INV-10 does not name outgoing settlement. The behaviors are approved at Specs HEAD, so this is a traceability gap, not a behavior defect. Recommended action: JDC decides whether to advance the Specs pin to a commit or version containing `828b351` and update the work item, or to record the exception. Until then, the create-duplicate and negative-settlement behaviors cite decisions outside the pinned version.

2. **Minor: No in-repo test for several hold-terminal refusals.** `tests/integration/test_outgoing_ach.py` does not test settle twice, reject or cancel after settle, reject before submit, second return, or return after rejection. The Tester attack file covers them and they pass, so the gap is coverage only. Recommend adding them to the repo suite.

3. **Minor: Refusal tests do not prove "no write".** The restricted/closed test asserts the error code only; the duplicate-movement test has no unchanged-state assertion. The Tester's copy checks business-table state and it holds.

4. **Minor: Double-return protection rests on a state check plus a ledger primary key.** If the state check were removed (M3), the caller gets `INTERNAL_ERROR` (a 500-class outcome) rather than the declared 409 `INVALID_TRANSITION`. The current code is correct, but no test pins the clean refusal.

5. **Minor: `finalize_hold` does not check the update row count.** The `WHERE state = 'active'` guard is correct, and the caller pre-checks `hold_state` in the same transaction, so this is safe today. A future caller that skips the pre-check would silently finalize nothing.

6. **Process note (Tester environment, not a product defect).** While setting up mutant copies, a broad `rm -rf` on a shared scratchpad mutants directory failed on a busy subfolder. Earlier mutant subfolders from another session are still present; one of them is now empty. I did not otherwise touch those folders. The Code repo and main checkout were not modified. The Tester worktree was removed with `git worktree remove` (no force) and `git worktree list` shows no leftover from this run.

## Not verified

- Concurrency and fault barriers under real parallel writers (TASK-18); only the single-transaction injected fault was exercised.
- HTTP routes, envelopes, and status mapping for API-07..11 and API-22 (TASK-25); tests were at the application/storage layer.
- Outgoing movements on a closed account (TASK-21 closure rules); return on a closed account is accepted per the Builder decision, not independently reviewed against closure rules.
- Outgoing restriction set and clear (TASK-20); only the stored restriction value was exercised.
- CI on the PR head (pinned Python 3.12.15 and the `quality-gates` and `validate-governance` workflows); only local gates were run.
- The local Specs checkout is at `ed6c1ce`, not the pin; pinned content was read with `git show` at `32befdaa` and HEAD.
- Ponytail review and Specs Updater outputs were not evaluated; they are not authority.
