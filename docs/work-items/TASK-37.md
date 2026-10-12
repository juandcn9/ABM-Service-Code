# Work item: TASK-37 — multi-process isolation for one database file

**Status:** Verified

Tester PASS on the merged revision `e6cbe81` (PR #115; implementation PR #114 merged `96199fc`; the first pass FAIL on `96199fc` findings F-01 and F-02 are resolved): `docs/evidence/TASK-37-tester-report.md`. JDC decided Verified on the criteria: Tester PASS on the merged revision, acceptance met.

## Authority

- Specs version and exact SHA: `v1.9.12` / `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f` (Code pin). Specs `main` includes TASK-37 (PR #61, `103e0e7`), DEC-0071, and the TASK-11 trigger correction (PR #62).
- TASK and affected IDs: `TASK-37`; `TEST-14` (concurrency, in multi-process form); `TEST-17` (restart, multi-process form); `DEC-0071` (owns the TASK-11 scheduled item: cross-process snapshot isolation and real multi-process SQLite locking).
- Dependencies: `TASK-28` (Verified; merged `48d7c13`).
- Gate: not a release gate unless JDC decides otherwise (Specs TASK-37 row).
- Owner role: Builder (Claude Code); independent Tester verification of the merged head is required.

## Scope

- Objective: prove, with separate OS processes on one database file, that the persistence layer keeps its guarantees: writers serialize, a reader keeps its snapshot, and a busy file gives a safe refusal with no partial effect.
- Included:
  1. `tests/integration/multiprocess_worker.py`: one process that drives the entry point against the shared file (a transfer or an incoming settlement), waiting for a go signal on stdin before it acts.
  2. `tests/integration/test_multiprocess.py`:
     - Contention: two processes spend the same funds at the same time; exactly one succeeds (201), the other is refused (422 `INSUFFICIENT_FUNDS`); the balance is never negative.
     - Busy: a process started first is refused with 503 `SERVICE_BUSY` while another process holds the write lock; the balance is unchanged afterwards.
     - Snapshot: a reader process holds a read transaction while a writer process commits a credit; the reader still sees its old balance inside the transaction and the new balance after it ends.
- Explicit exclusions:
  - No change under `src/` (the persistence layer already uses WAL, `BEGIN IMMEDIATE`, and a bounded busy timeout).
  - Power loss, disk failure, network filesystems, and more than one service instance (the Specs topology is a single writer per volume, DEC-0055).
  - Throughput or latency claims.

## Acceptance evidence

- Focused tests: `tests/integration/test_multiprocess.py` passes; each test asserts outcomes and stored state, not timing.
- Failure cases: two successes on the same funds; a negative balance; a busy refusal that changes state; a reader that sees another process's uncommitted or late commit.
- Required broader gates: full pytest, ruff check and format, mypy, both validators, and CI on the exact PR head.

## Implementation notes

- Each worker is a separate process with its own connection; the parent starts the go signal only after every worker has reported READY, so the race starts together.
- The observability events share stdout with the result lines; the parent skips event lines until it reads the line it needs.
- A busy test must start the worker before taking the write lock: a worker that starts while the file is locked is correctly unready, which is a different case.

## Non-claims (until implemented and tested)

- No cross-host, network-filesystem, or multi-instance claim.
- No throughput, concurrency-limit, or scaling claim beyond the tested contention cases.

## Completion

- Code commit/PR: PR #114 (merged `96199fc`) and the overlap fix PR #115 (merged `e6cbe81`).
- Commands/checks and results: `tests/integration/test_multiprocess.py`: 3 passed on three repeated runs; mypy and ruff pass.
- Review findings/resolution: first Tester FAIL (F-01 Major: contention workers did not overlap; F-02 Minor: busy wait unbounded) fixed in PR #115; re-pass PASS on `e6cbe81`; repeat runs 5 of 5 clean.
- Residual risks: the tests run on Windows and on the CI runner (Linux); the lock behaviour under SQLite WAL is the library's, not verified beyond these cases.
- Next safe action: open the Code PR, run CI, then the Tester pass on the merged head.
