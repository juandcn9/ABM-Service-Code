# TASK-28 Tester report (re-pass on merged revision)

**Task:** TASK-28 restart continuity and abrupt-termination recovery (TEST-17, NFR-03). **Merged commit:** 48d7c13 (PR #112). **PR head:** 20aa5a3. **Prior merged:** 4acd135 (PR #111, first pass FAIL). **Specs pin:** 1f6a26d. **Date:** 2026-10-11. **Role:** fresh-context Tester, read-only.

## Gates on 48d7c13

| Gate | Result |
|---|---|
| pytest | `993 passed, 1 warning in 151.33s` |
| ruff check . | passed |
| ruff format --check . | 163 files already formatted |
| mypy src harness tests scripts | exit 0 |
| validate_governance.py | exit 0 |
| validate_toolchain.py | exit 0 |
| `git diff --stat 4acd135 48d7c13 -- src/` | empty |

## Finding resolution

| ID | First pass | Now |
|---|---|---|
| F-01 graceful test compared the file to itself | Major | Resolved: EXPECTED_ACCOUNTS and EXPECTED_MOVEMENTS are asserted and match a fresh run of the sequence |
| F-02 abrupt test did not assert the child's step count | Major | Resolved: `done == killed_after` |
| N-01 kill point not deterministic | Note | Resolved by code reading: the child waits on stdin after each step; the recovered file must equal the clean prefix |
| F-03 reopen with the first connection still open | Minor | Open, scheduled |
| N-02 expected accounts omit the status column | Note | Open, scheduled |

## Mutants (scratch copies of 48d7c13)

| Mutant | Result |
|---|---|
| (a) correction returns 201 without writing | killed (graceful test: 450 != 460) |
| (b) child exits before the sequence | killed (child reported 0 steps, expected 3) |
| (c) recovered file replaced by an empty database | killed (all three parametrizations) |

No survivors.

## Verdict

**PASS.** No Blocker or Major findings.

## Not verified

- Repeated runs for flakiness of the subprocess test (one run on Windows).
- POSIX SIGKILL behaviour.
- Stress timing of the stdin handshake.
- F-03 was checked by code reading only.
