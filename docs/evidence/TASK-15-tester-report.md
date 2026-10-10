# TASK-15 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only with respect to the Code repo (no edits, commits, pushes, or config changes). The Tester did not build TASK-15 and reviewed the merged revision from its work item, Specs links, and code.

Revision verified: merge commit `436ee56e9fd9b00fbc25b122f9e06c7c480bdf26` (PR #24, `task-15-internal-transfer`, merged to `main`). Detached worktree at that SHA; `git rev-parse HEAD` confirmed the SHA before any check.

Specs pin in the revision: `v1.3.0` / `8250d21d5c800a31f5dab4bdd1a31bfeb396a056`, plus DEC-0025.

Environment: Windows 11; repo `.venv` Python 3.12.10 (CI pins 3.12.15, not re-run here); pytest 9.1.1 with `-p no:cacheprovider`; local Specs checkout at `ed6c1ce` (later than the v1.3.0 pin; text was compared, see Not verified).

## Result

PASS with findings. Blocker 0, Major 1, Minor 3. All gates pass. One mutant (removing the source-side closed-account check) survives because no test closes the source account.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| HEAD confirmed | PASS | HEAD = `436ee56e9fd9b00fbc25b122f9e06c7c480bdf26`, the merge commit of PR #24. |
| `mypy src harness tests scripts` | PASS | exit 0; "Success: no issues found in 52 source files". |
| `pytest -q` (full suite) | PASS | exit 0; 572 passed in 160.70s. |
| `ruff check .` | PASS | exit 0; "All checks passed!". |
| `ruff format --check .` | PASS | exit 0; "81 files already formatted". |
| `scripts/validate_governance.py` | PASS | exit 0; TASK-01 VALIDATION PASSED; Specs pointer v1.3.0 / 8250d21d. |
| Work item acceptance: equal debit and credit, one completed movement, two ledger effects, trace | PASS | `test_a_transfer_moves_equal_amounts_in_one_completed_movement` checks balances 700/300, two ledger rows (`transfer_source_debit`, `transfer_destination_credit`), movement `completed` with counterparty, trace row. |
| Insufficient funds: refused, no write except outcome | PASS | `test_insufficient_funds...` asserts movements/ledger/trace/holds unchanged and one 422 outcome stored. Code checks `current - held < cents` before any write. |
| Hold on source reduces available funds | PASS | `test_a_hold_on_the_source...`; code uses `current - held` from active holds. |
| Restricted source refused (OUTGOING_BLOCKED); closed account refused (ACCOUNT_CLOSED) | PASS with gap | Restriction tested on source. Closed tested on destination only; source-closed branch untested (see Finding 1). |
| Unknown account is ACCOUNT_NOT_FOUND; same account is VALIDATION_ERROR, no write | PASS | Test covers both; code returns VALIDATION_ERROR before `work` runs. The schema CHECK `counterparty <> account` is a second guard. |
| Caller without role refused before write | PASS | `FORBIDDEN_SCOPE` from `authorize` before any transaction. |
| Replay returns stored outcome; changed request is IDEMPOTENCY_CONFLICT | PASS | Replay path in `run_idempotent` compares fingerprint; no writes on replay or conflict. |
| Storage fault on destination rolls everything back | PASS | `test_a_storage_fault...` patches `apply_balance` for destination; counts and balances unchanged. The fault is raised after the source debit and movement write, so it covers the between-legs failure. `write_transaction` rolls back on any exception (`database.py`). Asserts only `Failure`, not the error code. |
| Database reopens ready with balances intact | PASS | `test_the_database_is_ready_after_transfers_and_a_restart`. |
| Duplicate movement id is INVALID_TRANSITION with no business write | PASS | `test_a_reused_movement_id_under_a_new_key...`; movement/ledger/trace counts and balances unchanged. A deterministic rejection row is stored in `idempotency_outcomes` (DEC-0011 design, matches DEC-0025 and the openapi `x-replay-result`). |
| Source and destination in one transaction | PASS | Single `uow.write()` (`BEGIN IMMEDIATE`) wraps movement, both ledger rows, both balance updates, trace, and outcome. |
| Contract alignment (API-12 and DEC-0025) | PASS | `contracts/openapi.yaml` at `/v1/transfers/internal` declares 201 success, replay 404 ACCOUNT_NOT_FOUND, 409 INVALID_TRANSITION, 422 ACCOUNT_CLOSED / INSUFFICIENT_FUNDS / OUTGOING_BLOCKED. The code's storable set matches. DEC-0025 is in `governance/decisions.md` as "Approved (JDC, 2026-10-10, option A)". specs/02 "Internal transfer" section matches. |

## Mutants

Each mutant was written in a self-contained copy (src, tests, harness, migrations, pyproject.toml), mutated by a script that asserts each target string occurs exactly once, and tested with `tests/integration/test_transfers.py` run from inside the copy.

| Mutant | Change | Result | Caught by |
|---|---|---|---|
| m1-no-dest-credit | Remove `tx.apply_balance(destination, cents)` | CAUGHT (4 failed, 7 passed) | equal-amount transfer, storage fault, restart, reused-id tests |
| m2-no-src-closed-check | Check only destination status for ACCOUNT_CLOSED | SURVIVED (11 passed) | none; no test closes the source account |
| m3-no-rollback | Remove the ROLLBACK in `write_transaction` (database.py) | CAUGHT (1 failed, 10 passed) | storage fault test (counts show uncommitted movement and ledger rows) |
| m4-no-dup-check | Replace the `get_movement` duplicate check with `if False:` | CAUGHT (1 failed, 10 passed) | reused movement id test |

Mutant results: 3 of 4 caught. The surviving mutant is a real test gap (Finding 1).

## Findings

1. **Major: source-side ACCOUNT_CLOSED is untested.** The work item acceptance says "a closed account take no transfer", and the brief asks for ACCOUNT_CLOSED on either side. The test closes only `acct-b`. Mutant m2 removes the source status check and every test still passes. The current code is correct on reading. Fix: add a test closing the source and asserting ACCOUNT_CLOSED with no write.
2. **Minor: one audit trace row per account for each transfer.** The code writes two `audit_trace` rows (source debit and destination credit), a Builder choice recorded in the work item. specs/02 and the contract describe "accepted trace" in the singular. Reversible, but it should be confirmed by JDC or the Specs owner, or recorded in DEC/gaps.
3. **Minor: the storage-fault test asserts only `Failure`.** It does not assert the error code (INTERNAL_ERROR or the mapped code), so a change in how the fault maps would pass unnoticed.
4. **Minor: currency mismatch is not tested in the transfer tests.** specs/02 lists currency-mismatched requests as rejected. The code calls `require_usd` in the validation block, but `test_transfers.py` has no case for it.

Not a finding: a deterministic INVALID_TRANSITION stores an idempotency outcome row. This is the stated design (DEC-0011 and DEC-0025), and it matches the contract.

## Not verified

- The local Specs checkout is at `ed6c1ce`, not the pinned `8250d21d`. I read the relevant text from the newer checkout; I did not confirm that the pinned commit has identical text.
- CI (pinned Python 3.12.15, GitHub checks on the PR head) was not re-run; only the local gates.
- Concurrency across processes (out of scope, TASK-18).
- API routes and envelopes (TASK-25) were not exercised; checks were at the application and persistence layer.
- The full suite ran once; the mutant runs used only the focused transfer test file. Other test files were not run against the mutants.
- The mutant copies are kept in the scratchpad (`m1-no-dest-credit`, `m2-no-src-closed-check`, `m3-no-rollback`, `m4-no-dup-check`); they were not removed because the removal guard blocked a deletion, and they are not part of the Code repo.
- No independent Ponytail review or fresh-context code review was run; this is a Tester pass only.
