# Work item: TASK-28 — automated restart continuity and abrupt-termination recovery

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.12` / `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f` (Code pin). Specs `main` is at the merge of PR #59 (TASK-36 status cell).
- TASK and affected IDs: `TASK-28`; `NFR-03` (restart preserves exact committed state and idempotency results, TEST-17); `NFR-04` and `NFR-05` (TEST-16, TEST-14, already automated in part); `NFR-08` (recovery limited to restart on the intact volume; no backup claim); `TEST-16`, `TEST-17`, `TEST-38`.
- Specs references: `specs/07-operations-and-recovery.md` section 5 (restart acceptance sequence, steps 1 to 7) and section 3 (readiness after restart).
- Dependencies: `TASK-27` (Verified).
- Owner role: Builder (Claude Code); independent Tester verification of the merged head is required.

## Scope

- Objective: prove restart continuity (graceful stop, and abrupt termination) on the same database file, following the Specs §5 sequence, with automated tests that run in CI.
- Included:
  1. `tests/integration/test_restart_continuity.py`:
     - Graceful restart: start on an empty file, apply migrations, run the sequence in `tests/integration/continuity_sequence.py` over HTTP on the real entry point (registration of two accounts; incoming ACH notice and settlement; internal transfer; outgoing ACH create, submission and settlement; card authorization and clearing; risk restriction; correction). Legal hold (non-public port) and closure are not in this sequence; their restart behaviour stays covered by the existing retention and closure tests, and is a recorded limit. record balances, states, history sequence and trace cutoff, close the connection, reopen the same file, and assert: readiness is clean, every snapshot value is identical, and a prior idempotency key replays the stored response with only replay metadata changed.
     - Abrupt termination: a subprocess runs the same commands and prints one line per committed command; the parent kills it at a chosen command, reopens the file, and asserts that every printed command is fully present and the in-flight command is either fully present or fully absent (never partial), with readiness clean and balances equal to the sum of the ledger.
  2. CI: the existing `quality-gates` job runs these tests through `pytest` (no new job).
- Explicit exclusions:
  - Backup, restore, disaster recovery, RPO, RTO (NFR-08; TASK-29 verifies the absence of claims).
  - Container-level restart (TASK-27 check and TASK-36 smoke already cover the image; the same-volume container restart is in `scripts/check_container.py`).
  - New application behaviour, routes or schema changes.

## Acceptance evidence

- Focused tests: `tests/integration/test_restart_continuity.py` passes; each assertion is stated on outcome and state, never on timing.
- Failure cases: a missing committed command after restart; a partially applied command; a replay that changes the stored response; readiness false after restart.
- Required broader gates: full pytest, ruff check and format, mypy, both validators, CI on the exact PR head.
- Documentation and trace updates: this work item.

## Implementation notes

- The restart uses the same file and a fresh connection, matching the container's behaviour (one process per volume, DEC-0055).
- The subprocess kill is deterministic: the parent waits for a printed line before killing, so the test does not depend on timing.

## Non-claims (until implemented and tested)

- No backup, restore, disaster-recovery, RPO or RTO claim.
- No claim about concurrent restarts or about a second process on the same volume.

## Completion

- Code commit/PR: implementation on branch `feat/task-28-continuity`; PR not yet opened.
- Commands/checks and results: `tests/integration/test_restart_continuity.py`: 4 passed (graceful restart with exact replay; three abrupt kills, each recovering to a clean prefix).
- Review findings/resolution: pending.
- Residual risks: the abrupt kill is an OS-level kill of a Python process; it does not simulate power loss or disk failure.
- Next safe action: implement the graceful and abrupt continuity tests, then open the Code PR.
