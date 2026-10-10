# TASK-21 Tester report

**Verdict: PASS on the fixed head `c7c5048`** (Code PR #70, merged as `6653ce1`). The first head `7729b9c` failed on one Major, fixed in `c7c5048`. Scheduled Minors are listed below.

## Subjects

- Code: `c7c5048`, branch `feat/task-21-closure`. Files: `src/abm/application/closure.py`, `src/abm/persistence/readiness.py`, `src/abm/persistence/sqlite_store.py`, `src/abm/ports/storage.py`, `tests/integration/test_closure.py`.
- Specs: `v1.9.2`, `3866d63fc22079acc040be096a760d1660eec09a`.
- Work item: `docs/work-items/TASK-21.md` (PR #69, merged as `c116bad`).

## Pass 1 (head `7729b9c`): FAIL, one Major

- Readiness reported `INTEGRITY_FAILED` after a permitted late clearing followed by a full refund. The post-closure clearing clause checked only `late_cleared`, and a refund moves the movement to `refunded`. The suite missed it because its clock never advanced past closure.
- Fix in `c7c5048`: the clause accepts `late_cleared` and `refunded`, and a new test advances the clock through clearing and refund. The test fails on the old rule.

## Pass 2 (head `c7c5048`): PASS

| Command | Exit | Result |
|---|---|---|
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 113 files already formatted |
| `mypy src harness tests scripts` | 0 | No issues in 64 source files |
| `pytest -q` | 0 | 755 passed |
| `scripts/validate_governance.py` | 0 | Passed (Specs v1.9.2) |

Mutants: reverting the clause to `<> 'late_cleared'` is caught by the time-advancing test. Removing the settlement clause is not caught by the settlement test on its own, because the balance check also flags that row (Minor 1).

Card clearing after closure is flagged for `authorized_with_hold`, `reversed` and `cleared`, and permitted for `late_cleared` and `refunded` (probe, five cases).

## Spec-to-test trace

| Rule | Test |
|---|---|
| INV-15 / API-18: nonzero balance refused, nothing written | `test_a_nonzero_balance_blocks_closure_and_writes_nothing` |
| INV-15: active hold refused at zero balance | `test_an_active_hold_blocks_closure_even_at_zero_balance` |
| DEC-0044: pending, accepted_with_hold blocked | `test_an_unresolved_movement_blocks_closure`, `test_a_movement_awaiting_settlement_blocks_closure` |
| DEC-0044: settled, cleared, reversed, expired do not block | Covered by drained and reversed cases; settled outgoing checked by probe |
| DEC-0042: restriction unchanged; accepted on closed | `test_eligible_closure_is_terminal_and_keeps_the_restriction`, `test_a_restriction_is_accepted_on_a_closed_account` |
| Re-close is INVALID_TRANSITION | `test_eligible_closure_is_terminal_and_keeps_the_restriction` |
| INV-16: customer instructions refused with ACCOUNT_CLOSED | `test_a_closed_account_refuses_new_customer_instructions` |
| INV-16: late clearing, refund, incoming return, correction permitted; no reopen | `test_permitted_late_evidence_after_closure_does_not_reopen_the_account`, `test_late_clearing_then_refund_after_closure_is_clean_with_time_advancing` |
| INV-18: post-closure settlement flagged | `test_a_post_closure_settlement_is_reported_by_readiness` |
| API-18: wrong role and unknown account | `test_closure_by_another_role_or_an_unknown_account_is_refused` |
| Replay without a second trace | `test_replay_returns_the_stored_closure_without_a_second_trace` |

## Scheduled Minors

1. The settlement readiness test does not isolate its clause, because the balance check flags the same inserted row. Owner Builder. Trigger TASK-23.
2. The `submitted` blocking case and the settle-side ACCOUNT_CLOSED branch are not tested. Owner Builder. Trigger TASK-23.
3. Same-second post-closure effects are not flagged (documented shortcut). Owner Builder. Trigger: a later hardening task.

## Not verified

- The HTTP route, envelope, and status mapping for API-18 (TASK-25).
- Retention dates after closure (TASK-22).
- Concurrent closure against live instructions.
- Movement states beyond the five probed for card clearing (for example `expired`, `corrected`).
