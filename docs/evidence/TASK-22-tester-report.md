# TASK-22 Tester report

**Verdict: PASS on the merged head `caacace`** (Code PR #74, merged as `9811a61`). Two passes were run. Pass 1 (`07d12eb`) found two Majors: missing late-event advance tests, and legal-hold refusals with no approved trace. Both were fixed: the tests were added in `caacace`, and the refusal rule was approved as DEC-0047.

## Subjects

- Code: `caacace`, branch `feat/task-22-retention`. Files: `src/abm/application/retention.py`, `src/abm/application/legal_hold.py`, finalize calls in `closure.py`, `incoming_ach.py`, `outgoing_ach.py`, `cards.py`, `corrections.py`, store and port changes, and three new test files.
- Specs: `v1.9.4`, merge `f4f4f2061739c5b2a20c0e4715f2caeecd3bb2b4`, including DEC-0046 (retention dates stored) and DEC-0047 (legal-hold refusal rule).
- Work item: `docs/work-items/TASK-22.md` (PR #73, merged as `534ee02`).

## Pass 1 (`07d12eb`): conditional PASS, two Majors

1. Four permitted late events had no advance test (outgoing return, correction, card late clearing, card refund). Removing the refund's advance went uncaught. Fixed: `tests/integration/test_retention_late_events.py`. Removing the refund's advance now fails a test.
2. The legal-hold requested-state refusal and its stored outcome had no approved trace. Fixed: recorded as DEC-0047 (option a).

## Pass 2 (`caacace`): PASS

| Command | Exit | Result |
|---|---|---|
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 120 files already formatted |
| `mypy src harness tests scripts` | 0 | No issues in 69 source files |
| `pytest -q` | 0 | 770 passed |
| `scripts/validate_governance.py` | 0 | Passed |

Mutants (two new files): removing the outgoing-return advance, the correction advance, or the card refund advance is caught. Changing the legal-hold refusal to a success is caught. Removing the incoming-return advance is caught only by `tests/integration/test_retention.py`, not by the new files (Minor 1).

DEC-0047 check: a repeated set or clear returns `INVALID_TRANSITION`, stored, with no write. `ACCOUNT_NOT_FOUND` is stored. A `record_type` or `record_id` mismatch returns `VALIDATION_ERROR` and is not stored.

## Scheduled Minors

1. The docstring of `test_retention_late_events.py` says it covers every late event, but the incoming return is covered only by `test_retention.py`. Owner Builder. Trigger TASK-23.
2. The README on `main` still states Specs `v1.9.0`, which predates the pins since then. This predates TASK-22. Owner Builder. Trigger: a docs-only fix before the next release.

## Not verified

- The HTTP route for legal hold or retention (none exists; TASK-25). TEST-37 holds only at the application level.
- The clock-regression case: `finalize` overwrites the dates with `now` without a monotonic check. The clock is monotonic in the harness.
- Concurrency and fault injection for the legal-hold path.
