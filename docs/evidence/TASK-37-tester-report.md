# TASK-37 Tester report (re-pass on merged revision)

**Task:** TASK-37 multi-process isolation (DEC-0071). **Merged commit:** e6cbe81 (PR #115). **PR head:** 4515b6d. **Prior merged:** 96199fc (PR #114, first pass FAIL). **Date:** 2026-10-11. **Role:** fresh-context Tester, read-only.

## Gates on e6cbe81

| Gate | Result |
|---|---|
| pytest | `996 passed, 1 warning in 163.64s` |
| ruff check . | passed |
| ruff format --check . | 167 files already formatted |
| mypy src harness tests scripts | exit 0 (96 files) |
| validate_governance.py | exit 0 |
| validate_toolchain.py | exit 0 |
| `git diff --stat 96199fc e6cbe81 -- src/` | empty |

## Finding resolution

| ID | First pass | Now |
|---|---|---|
| F-01 contention workers did not overlap | Major | Resolved: both go signals are sent before either result is read |
| F-02 busy wait unbounded | Minor | Resolved: the busy test asserts the refusal within five seconds |

## Repeat runs (tests/integration/test_multiprocess.py)

Five of five runs passed, three tests each.

## Mutants

| Mutant | Result |
|---|---|
| (a) deferred BEGIN instead of BEGIN IMMEDIATE | contention test fails 3 of 3 runs (second writer gets 503 SERVICE_BUSY instead of 422) |
| (b) busy-test worker timeout 60000 ms | busy test fails on the five-second bound (65.9 s) |
| (c) reader committed before writer | snapshot test fails |

## Verdict

**PASS.** No Blocker or Major open.

## Not verified

- POSIX behaviour (run on Windows only).
- Multi-host operation.
- Note: stale worker processes from an earlier debugging session were found and stopped after the run; they are not part of the result.
