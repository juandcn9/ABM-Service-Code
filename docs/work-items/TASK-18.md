# Work item: TASK-18 — concurrency barriers and fault injection; funds protection, final-effect uniqueness, and rollback

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.8.4` / `618a7eb5ac1707ac99fea845562ec39afd124f0a`
- TASK and affected IDs: `TASK-18`; `TEST-14` (concurrent debits), `TEST-38` (busy, disk-full and fault return a safe failure with no partial effect); `BT-03` (funds protection); `INV-05`, `INV-06`, `INV-09`, `INV-10`, `INV-11`; `NFR-05`, `SEC-08`
- Protocols: `specs/08-verification.md` section 6 (concurrency: independent connections, a barrier before `BEGIN IMMEDIATE`, record start order, commit or rollback, outcome and final state; no timing as the assertion) and section 7 (fault injection: controlled exception before and after each insert or update and before commit; reopen and compare with the pre-command snapshot; kill a subprocess during a write and verify recovery and invariants)
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required
- Dependencies: `TASK-13` through `TASK-17` merged and recorded Implemented (true on `main` at `e0a7adb`)

## Acceptance (paraphrased from the Specs; TEST-14 and TEST-38 are the sources)

- Two concurrent debits against the same available funds produce at most one success and never a negative available balance (TEST-14).
- Concurrent settlements or returns of the same movement produce exactly one final effect (final-effect uniqueness).
- A service-busy, disk-full or simulated fault returns a safe failure and leaves no partial or orphaned effect (TEST-38).
- Injected exceptions before and after each insert or update and before commit leave the database equal to the pre-command snapshot after reopen (section 7 rollback).
- Killing a subprocess during a write leaves a database that SQLite recovers, with all invariants holding (section 7 recovery).

## Scope

- Tests and, only if a test proves a gap against the Specs, the minimal fix. Any fix is recorded as a Code change with regression evidence, and the Builder stops for JDC if the Specs are unclear.
- Concurrency tests use independent SQLite connections and a barrier, as section 6 requires.
- Fault injection is verification-mode only (no production hook).

## Non-claims

- No production concurrency or scale claim (DEC-0003: single-writer demonstration store).
- Backup and restore are outside this task (NFR-03 recovery is intact-volume restart only).
- Closed-account card cases that set closure by direct SQL stay with TASK-21.
