# Work item: TASK-18 — concurrency barriers and fault injection; funds protection, final-effect uniqueness, and rollback

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.8.4` / `618a7eb5ac1707ac99fea845562ec39afd124f0a`
- TASK and affected IDs: `TASK-18`; `BT-01`, `BT-03` (funds protection); `INV-05`, `INV-06`, `INV-07`, `INV-08`, `INV-09`, `INV-10`, `INV-11`; `NFR-04`, `NFR-05`, `SEC-08`; `TEST-14` (concurrent debits), `TEST-16` (failure after every persistence step leaves all or no effects), `TEST-36` (effect uniqueness across retries and races), `TEST-38` (busy, disk-full and fault return a safe failure with no partial effect). The governing trace is `specs/08-verification.md` section 9.1.
- Protocols: `specs/08-verification.md` section 6 (concurrency: independent connections, a barrier before `BEGIN IMMEDIATE`, record start order, commit or rollback, outcome and final state; no timing as the assertion) and section 7 (fault injection: controlled exception before and after each insert or update and before commit; reopen and compare with the pre-command snapshot; kill a subprocess during a write and verify recovery and invariants)
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required
- Dependencies: `TASK-13` through `TASK-17` merged and recorded Implemented or Verified (true on `main` at `e0a7adb`)
- Routed Minor: the M09 kill test (a deferred-`BEGIN` mutant caught only by thread timing, from the TASK-06 report) is owned here (Specs status file, scheduled Minors).

## Acceptance (paraphrased from the Specs; sources are TEST-14, TEST-16, TEST-36, TEST-38 and section 7)

- Two concurrent debits against the same available funds produce at most one success and never a negative available balance (TEST-14).
- Concurrent settlements or returns of the same movement produce at most one ledger effect and at most one evidence item per movement and effect kind, while allowing the defined offset pair (settlement and return, clearing and refund) (TEST-36).
- Injected failure after every persistence step leaves each command with all of its effects or none (TEST-16).
- A service-busy, disk-full or simulated fault returns a safe failure and leaves no partial or orphaned effect (TEST-38).
- Injected exceptions before and after each insert or update and before commit leave the database equal to the pre-command snapshot after reopen (section 7 rollback).
- Killing a subprocess during a write leaves a database that SQLite recovers, with all invariants holding (section 7 recovery).
- The M09 mutant (BEGIN deferred instead of immediate) is caught by a barrier-based test, not by timing (routed Minor).

## Scope

- Tests and, only if a test proves a gap against the Specs, the minimal fix. Any fix is recorded as a Code change with regression evidence, and the Builder stops for JDC if the Specs are unclear.
- Concurrency tests use independent SQLite connections and a barrier, as section 6 requires.
- Fault injection is verification-mode only (no production hook).

## Non-claims

- No production concurrency or scale claim (DEC-0003: single-writer demonstration store).
- Backup and restore are outside this task (intact-volume restart only).
- Closed-account card cases that set closure by direct SQL stay with TASK-21.

## Implementation and evidence (2026-10-10)

- Code PR #57, merged to `main` as `2eb7a4c` (merged head `da05269`). JDC approved the exact head (in the session, 2026-10-10) `da05269ffc7c14070e7d0218e2e00301388acf57`.
- Tests only: concurrency and fault-injection files (724 tests passing).
- Tester record: [`docs/evidence/TASK-18-tester-report.md`](../evidence/TASK-18-tester-report.md).

## Scheduled items

- Outgoing settlement evidence guard not distinguished by the TEST-36 races. Owner Builder. Trigger: TASK-18 follow-up.
- M09 deferred-BEGIN mutant not named by the new tests (TASK-06 test is its only detector). Owner Builder. Trigger: TASK-18 follow-up.
- Subprocess kill lands after the first balance update, not during COMMIT; faults are simulated. Owner Builder. Trigger: a later hardening task.
- Test hygiene in the concurrency and fault files. Owner Builder.
- TASK-07 item: `synchronous = FULL` is not discriminated by the tests (routed here by the Specs status file). Owner Builder. Trigger: TASK-18 follow-up.
- TASK-15 item: the storage-fault test does not assert the error code (routed here by the Specs status file). Owner Builder. Trigger: TASK-18 follow-up.

## Non-claims

- No production concurrency or real disk-full claim.
- The `specs/09` row for TASK-18 still reads Draft; its status change is normative and needs JDC approval.

## Process record

- Independent review evidence was not stated in the Code PR description before merge, and the evidence file was committed after the merge. This does not meet the merge rule in `docs/governance/repository-policy.md` ("Approval and merge authority"). Found in the TASK-22 review on 2026-10-10. Recorded here so the Verified decision is made with it in view.

## Remediation (Tester FAIL on `da05269`)

- F1 (Major): TEST-16 "each command" was verified for two of about eleven write commands. Fix: `test_every_write_command_leaves_the_pre_command_snapshot_under_a_fault` in `tests/integration/test_fault_injection.py` runs the before, after, and before-commit sweep for every command: the 16 in the conformance table plus `close_account`, `set_risk_restriction`, `set_legal_hold`, and `create_correction`, for four error kinds (80 cases). It also found that the write-method list omitted `set_restriction`, `close_account`, `set_retention_dates`, and `set_legal_hold`; those are now instrumented.
- F2 (conditional Major, the M09 acceptance bullet): `test_a_second_writer_is_refused_while_a_write_transaction_is_open` in `tests/integration/test_concurrency.py`. It is deterministic and uses no timing or thread race: a second connection with `busy_timeout = 0` must be refused while the first holds `write_transaction`, and it proceeds after the commit. Mutation: changing `BEGIN IMMEDIATE` to a deferred `BEGIN` fails the test; the source was then reverted to its committed form.
- Checks on the fix head: `ruff check`, `ruff format --check`, `mypy src harness tests scripts` pass; the full-suite run and a fresh Tester pass on the fix head are pending.

## Verified record

- Remediation of the TASK-18 Tester FAIL on `da05269` (F1 sweep coverage, F2 M09 probe). Fix branch head `c29f895` (guard for F3) was merged to `main` as `1a1eade` (PR #125); the test files on `main` are identical to the tested head.
- Independent Tester PASS with findings on `c29f895`: Blocker 0, Major 0. The earlier Minor F3 (no completeness guard) is closed by the guard test `test_every_sql_writing_method_is_instrumented`. Report: `docs/evidence/TASK-18-remediation-tester-report.md`.
- Tester observation, not blocking: the guard is a source-text regex heuristic, not a full static analysis.
