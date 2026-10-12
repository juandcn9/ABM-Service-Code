# Work item: TASK-07 — SQLite connection, transaction unit, and error mapping

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-07`; `INV-06`; `DATA-01` through `DATA-08`; `TEST-16`, `TEST-38` (persistence foundations only); `NFR-04`; `DEC-0003`
- Decision, gap, or risk records: `DEC-0003`, `RISK-0001`; no new decision or gap; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: open SQLite with the required strict settings, give the application one transaction unit that is all-or-nothing, and map SQLite failures to stable safe results.
- Included files/components: `src/abm/persistence/database.py` (`open_database`, `write_transaction`, `read_transaction`, `to_failure`, `DatabaseUnavailable`) and `tests/integration/test_database.py`.
- Explicit exclusions: repository interfaces and implementations (see Implementation notes); the startup sequence, readiness integrity gate, and `ABM_*` configuration parsing (`TASK-12`, `TASK-26`); idempotency, registration, and any financial table access (`TASK-10` onward); the HTTP mapping of `SERVICE_BUSY` and `SERVICE_UNREADY` (`TASK-25`).
- Dependencies and entry gate: `TASK-06` (migrations, PR #8). This branch also contains the `TASK-08` domain modules (`abm.domain.results`) by merge from the `TASK-08` branch because the error mapping returns the typed `Failure`; both were merged to `main` (PR #8 as `45f3880`, PR #9) and this work item is reviewed in PR #13.

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_database.py`, real SQLite files): foreign keys on, WAL, `synchronous=FULL`, and the configured busy timeout are applied and read back; the connection is autocommit with explicit transactions; foreign keys are enforced; a busy timeout outside 1..60000 ms, non-integer, or boolean is refused; an unopenable path raises a message that does not contain the path; a commit makes all steps visible together; an injected failure after every step (before the first, between, and after the last) leaves no effect; a constraint failure, a `KeyboardInterrupt`, and an unexpected exception all roll back; a second writer waiting on `BEGIN IMMEDIATE` times out with a retryable `SERVICE_BUSY` failure and leaves no partial row; four threads writing 20 rows each are serialized into contiguous blocks; a read transaction sees one consistent snapshot while another connection commits; a full database (`max_page_count` reached) gives `SERVICE_UNREADY` with no partial rows; unexpected driver errors map to `INTERNAL_ERROR` and never expose SQL or paths. Mutation check: removing the rollback makes three tests fail.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head, plus the same commands locally; the SQL static scan covers the new module (all statements are fixed literals).
- Failure, concurrency, authorization, and recovery cases: the cases above cover rollback, serialization, busy, and disk-full; a multi-process crash or `kill -9` recovery test belongs to `TASK-28`.
- Documentation/trace updates: README, CHANGELOG, this work item.

## Implementation notes

- Reversible technical choices: the busy timeout is installed by the connect `timeout` (PRAGMA values cannot be bound, and formatting one into SQL would trip the static SQL scan); bounds are 1..60000 ms with the Specs default of 5000. Settings are read back and a mismatch closes the connection and raises `DatabaseUnavailable`. An in-memory database is accepted for tests and reports `memory` journaling; every file database must report `wal`. One connection per unit of work or thread; sharing one connection across threads needs a caller-provided lock (the choice is left to the composition in `TASK-25`/`TASK-26`).
- Error mapping uses the primary SQLite result code (`sqlite_errorcode & 0xFF`): busy or locked gives `SERVICE_BUSY` (retryable); read-only, I/O, corrupt, full, cannot-open, or not-a-database gives `SERVICE_UNREADY`; anything else gives `INTERNAL_ERROR`. Messages are fixed text.
- Repository interfaces: the plan lists them, but `specs/03-architecture.md` forbids generic repository abstractions without three current uses and says the application owns the storage it needs. No aggregate exists yet, so empty protocols would be speculative. Each aggregate's interface is defined in the first task that needs it (`TASK-10` accounts and idempotency, then movements, holds, ledger, trace, evidence, retention). This is a scope interpretation for review, not a change to the requirement.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record; the PR is #13 (draft until the final head is reviewed and Tester-verified).
- Commands/checks and results: locally `pytest` 337 passed in this branch after merging `main` (includes the merged `TASK-06`, `TASK-08` and `TASK-09` tests), `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and both validators pass.
- Review findings/resolution: Builder Audit `ponytail-review` (installed plugin 5.1.0, `full`, DV-01): one Should-fix, a failed configuration step leaked the open connection; fixed by closing it. A fresh-context review and Tester verification of the final head are still required.
- Residual risks: `SQLITE_BUSY` inside an already-open write transaction (for example a checkpoint) is mapped like any busy error and the caller must treat the whole unit as failed; the `ABM_BUSY_TIMEOUT_MS` setting is not parsed yet; disk-full behavior was simulated with `max_page_count`, not a real full volume.
- Next safe action: `TASK-10` (idempotency, registration) once `TASK-07`, `TASK-08`, and `TASK-09` are merged; `TASK-12` for startup and readiness.

## Review fixes (PR #13, fresh-context review)

- Major 1: the busy timeout was rounded down by the driver, so 372 valid values (for example 1001) failed the readback check. The timeout now carries half a millisecond so every valid value applies exactly. A test checks every value from 1 to 60000; removing the half millisecond fails it (372 values).
- Major 2: the old serialization test passed without `BEGIN IMMEDIATE`. A new test has the second writer read the state inside its transaction while the first writer holds the lock. It waits, then sees the first commit. Changing to a deferred `BEGIN` fails it.
- Minor: the read snapshot docstring now says it starts at the first read; the readback queries run inside the error handler; every SQLite result code the module maps has its own test.
- Not changed, recorded: nested write or read inside another transaction is refused by SQLite and mapped to INTERNAL_ERROR (misuse only, no test); a body that commits on its own leaves the context manager's commit to fail (misuse only).

## Independent Tester evidence

- Revision: merge `5eab23f`. Report: [`docs/evidence/TASK-07-tester-report.md`](../evidence/TASK-07-tester-report.md).
- Result: PASS with findings: 0 Blocker, 0 Major, 2 Minor. Status stays Implemented until the Major findings are resolved.

## Verified record

- Tester PASS on the merged revision `5eab23f` (PR #13, `main`), with Blocker 0, Major 0, Minor 2: `docs/evidence/TASK-07-tester-report.md`.
- Scheduled items, each with an owner and a trigger:
  - Stale test count in this work item (337 locally; 420 passed at the verified merge). Owner Builder. Trigger: the next change to this work item.
  - `synchronous = FULL` is not discriminated by the tests, because the build default is already FULL. Owner Builder. Trigger: TASK-18 concurrency and durability tests.
