# TASK-16 independent Tester report, head `9ad984d` (merged as `69b01cf`)

**Provenance:** fresh-context Tester agent, read-only, detached worktree at the pinned SHA, run on 2026-10-13. The Tester made no commits, refs or config changes and removed its worktree afterwards. This record is the Tester's reported result; the raw session transcript is not committed.

**Subject:** branch `fix/task-16-closure-real-command`, head `9ad984d`, PR #145. The change is test-only: `tests/integration/test_cards.py`. The three closed-account card tests close `acct-1` through the real commands (`internal_transfer` drains the balance to `acct-2`, then `close_account`) instead of direct SQL. `src/` is unchanged from `1729ea2`. Merged as `69b01cf`; the merged tree equals the tree of `9ad984d`.

**Earlier head:** `823b5c9` passed with one Minor (the new helper `close_through_commands` had untyped parameters). It was fixed in `9ad984d` and the Tester re-ran on `9ad984d`.

## Gates

Python 3.12.10, existing project venv (no installs).

| Gate | Result |
|---|---|
| `scripts/validate_governance.py` | passed |
| `ruff check` | all checks passed |
| `ruff format --check` | 186 files already formatted |
| `mypy src harness tests scripts` | no issues in 101 files |
| targeted pytest: `tests/integration/test_cards.py`, `test_closure.py`, `test_risk_restriction.py`, `tests/security/test_block_resolution.py` | 62 passed, 0 failed |
| `pytest --collect-only -q -p no:cacheprovider` | 1293 collected |
| full pytest suite | not run (known stall on the review host in `test_concurrency.py`; CI is the authority for the full suite) |

## Checks

- `git diff` from `1729ea2` to `9ad984d` touches only `tests/integration/test_cards.py` (+49/-15); `src/` is unchanged.
- The three closed-account tests close the account through `close_account`; no `UPDATE accounts` closes an account in `test_cards.py`.
- Balance arithmetic in the refund test: 1000 funded, 400 cleared, 600 drained to `acct-2`, refund of 400 leaves `acct-1` at 400 and `acct-2` at 600.
- The helper `close_through_commands` and the three tests are type-annotated.
- HEAD was `9ad984d` before and after the checks.

## Mutation check

- In a Tester-owned copy: the `ACCOUNT_CLOSED` line in `src/abm/application/cards.py` was replaced with `pass`.
- Result: 1 failed, 36 passed in `tests/integration/test_cards.py`. The failing test is `test_authorization_on_a_closed_account_is_refused_and_writes_nothing`.
- The source file was reverted from a saved copy; its SHA-256 matched the original before and after.

## Findings

- Blocker: 0
- Major: 0
- Minor: 0

Verdict: **PASS** for TASK-16 at `9ad984d`: no open Blocker, Major or Minor finding.

## Not verified

- The full pytest suite on this head (see Gates).
- Other test files that still close accounts with direct SQL (`test_closure.py`, `test_incoming_ach.py`, `test_transfers.py`). They are outside TASK-16 and this change does not touch them.
- Helpers in `test_cards.py` other than `close_through_commands` (`funded`, `authorize`, `step`, `simple`) are not type-annotated. They predate this change and were not part of it.
