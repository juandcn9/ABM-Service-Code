# Work item: TASK-12 — startup migration, integrity, and fail-closed readiness

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-12`; `INV-18`; `NFR-02`; `SEC-10`; `API-20`, `API-21` (the readiness computation only); `TEST-18`; `TEST-30` (direct-corruption half)
- Decision, gap, or risk records: `DEC-0007`; no new decision or gap; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: the startup sequence (open with required settings, apply reviewed forward migrations in one transaction, verify the schema version, run integrity and invariant checks) and a read-only readiness computation that fails closed with controlled reason codes.
- Included files/components: `src/abm/persistence/readiness.py` (`start_database`, `readiness_reasons`, `StartupResult`, the six reason codes) and `tests/integration/test_readiness.py`; the SQL scan waiver now also lists this file for its fixed inconsistency queries.
- Explicit exclusions: the FastAPI `/health/live` and `/health/ready` routes and their JSON bodies (`TASK-25`); configuration parsing and the `CONFIG_INVALID` code, which needs the `ABM_*` settings (`TASK-26`/`TASK-27`); structured logging of failures (`TASK-26`); invariants over tables that later tasks fill (closure rules beyond a closed account holding an active hold, legal-hold consistency) which those tasks add with their data; any repair.
- Dependencies and entry gate: `TASK-06` (migrations) and `TASK-07` (connection). This branch also contains `TASK-08` to `TASK-10` by merge because the tests use registration to build a consistent database; the PR is opened after those PRs are merged.

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_readiness.py`, real SQLite files): an empty volume starts ready with `schema_version` recorded and foreign keys on; a restart on the intact volume stays ready, preserves state, and does not re-apply migrations; a newer schema, a foreign database, and an edited migration are never ready, leave no connection, and report `SCHEMA_UNSUPPORTED`; a garbage file, a missing directory, and a directory path report `DATABASE_UNAVAILABLE`; a locked database reports `DATABASE_BUSY` at startup and for an open connection, and recovers when the lock clears; direct corruption bypassing the immutability triggers makes readiness fail with `INTEGRITY_FAILED` for a projection that differs from the ledger, a ledger entry without its projection, an account without its registration trace or retention row, an accepted trace without its successful idempotency outcome, an active hold on a settled movement, a movement that needs a hold and has none, a transfer with unequal sides, and a closed account with an active hold; an orphan row reports `FOREIGN_KEY_FAILED`; damaged database pages are detected and left exactly as damaged; checks write nothing (a full dump is identical before and after); reason codes are only the controlled set.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head; the SQL static scan covers the new module (fixed statements; waiver pinned to two files by a test).
- Failure, concurrency, authorization, and recovery cases: busy, corruption, unsupported schema, and unopenable database are covered; abrupt termination and restart continuity with real traffic belong to `TASK-28`.
- Documentation/trace updates: README, CHANGELOG, this work item.

## Implementation notes

- Reversible technical choices:
  - Readiness returns a sorted list of reason codes (empty means ready). On an unsupported or missing schema it stops at `SCHEMA_UNSUPPORTED` because nothing else can be trusted. Otherwise it runs `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, the nine inconsistency queries from `specs/05` section 7, and a write-lock probe (`BEGIN IMMEDIATE` then `ROLLBACK`, which writes nothing).
  - Driver errors map to codes by their SQLite class: busy gives `DATABASE_BUSY`; corrupt, unreadable, or full storage gives `INTEGRITY_FAILED`; anything else gives `DATABASE_UNAVAILABLE`.
  - The transfer check compares the sum of source debits with the sum of destination credits per transfer, so it assumes nothing about which account column holds which side.
  - `start_database` closes the connection and returns no usable handle whenever the result is not ready.
- Active-hold, transfer, trace, and outcome checks are written against the schema and will first see data from `TASK-13` onward; their tests insert rows directly, so a later task that changes how it records movements must keep these queries true or update them with the Specs.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record; the PR is opened after the `TASK-06` through `TASK-10` PRs merge.
- Commands/checks and results: locally `pytest` 460 passed in this branch (CI 460 passed on the head) (includes the merged earlier tasks), `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and both validators pass.
- Review findings/resolution: fresh-context review of ce8b25d (FAIL: three Majors, all fixed in eb1a4e8); focused re-review of eb1a4e8 PASS with findings (no Blocker or Major); independent Tester pass of eb1a4e8 PASS (CI green on CPython 3.12.15). ponytail-review (Gate 8) of the remediation diff returned Ship, with no Must-fix or Should-fix finding (see the evidence report): `ponytail-review` for this branch (DV-01 applies).
- Residual risks: a very large database makes `PRAGMA integrity_check` slow at startup (acceptable for the single-writer demonstration, `RISK-0001`); the inconsistency queries encode the Builder's reading of `specs/05` section 7 and need a Tester pass against the Specs; readiness is computed on demand, so caching or rate limiting for the health route is a `TASK-25`/`TASK-26` decision.
- Next safe action: `TASK-11` (account reads and trace sequencing), after this PR merges.

## Wiring added before merge

- `readiness_reasons` now calls `retained_history_protected()` (deferred from TASK-06). A guard trigger removed or a retained table altered outside the runner reports `INTEGRITY_FAILED`; the Specs' six reason codes are unchanged. The object-set check catches a dropped trigger first, so `test_a_guard_trigger_removed_outside_the_runner_is_not_ready` does not exercise this call; `test_a_temp_object_on_the_checked_connection_is_integrity_failed` does.
- The direct-corruption test helper drops guard triggers to insert bad rows; that now counts as tampering, so the missing-account case expects `INTEGRITY_FAILED` as well as `FOREIGN_KEY_FAILED`.


## Specs check of the inconsistency queries (Tester, PR #15)

- Matches `specs/05-data-model.md` section 7: projection equals signed ledger sum; holds only for outgoing ACH in `accepted_with_hold|submitted` and card in `authorized_with_hold`, and every such movement has its hold; a hold reserves its own movement's account; no active hold on a closed account; transfer source debits equal destination credits; registration trace and retention row per account; every accepted trace has a committed successful outcome.
- Not yet checked, recorded as open: the explicit available-balance identity (posted minus active held must equal the projection; no separate column exists, so it is implied by the projection check), and the closure and finalized-effects rules, which need data from TASK-13 to TASK-21.

## Review fixes (PR #15, fresh-context review of ce8b25d)

- Major 1 (vacuous corruption evidence): the test helper dropped the guard triggers for every case, so the nine data checks were never the reason. `tamper()` now restores the guard triggers after the bad rows are written. Removing the inconsistency loop now fails 11 readiness tests.
- Major 2 (wrong code for a missing object): readiness now compares the set of tables, indexes, views and triggers with the set the reviewed migrations create. A mismatch is `INTEGRITY_FAILED` and stops before the data queries, so a missing table no longer surfaces as `DATABASE_UNAVAILABLE`. Covered by `test_a_missing_table_is_integrity_failed_not_database_unavailable`.
- Major 3 (index checks): the same object comparison covers indexes, so a dropped required index is `INTEGRITY_FAILED` (`test_a_dropped_index_is_integrity_failed`; specs/07 section 3 step 6).
- Minor: the controlled-codes test no longer asserts a string check that could never fail.
- Recorded, not changed: a non-migration exception from `apply_migrations` (or a rollback error) escapes `start_database` without a result; no connection is returned, so it is not fail-open. The static-scan waiver for `readiness.py` is file-wide (the fixed-statement rule); formatted-SQL detection still applies to the file.
- The temp-object check on the readiness connection is covered by `test_a_temp_object_on_the_checked_connection_is_integrity_failed`.

## Independent Tester evidence

- Revision: merge `e996304`. Report: [`docs/evidence/TASK-12-tester-report.md`](../evidence/TASK-12-tester-report.md).
- Result: PASS with findings: 0 Blocker, 1 Major (stored-idempotency JSON check not implemented, Specs 05 s7), 4 Minor. Status stays Implemented until the Major findings are resolved.

## Remediation of the Tester Major (2026-10-10)

- Gap closed: readiness now checks that stored idempotency responses are valid JSON (specs/05 s7) before `integrity_check`, and reports `INTEGRITY_FAILED`, not `DATABASE_UNAVAILABLE`. Regression test: `tests/integration/test_readiness.py` (malformed-row case); the test fails without the check. Code commit `43ffbfb` on branch `fix/majors-task-12-13-15`.
- Scheduled Minor (owner Builder, trigger TASK-25): the unsupported-schema branch of `readiness_reasons` has no direct test (mutant M1 in the Tester report); add it when readiness is computed on demand.

- Verified on merged head `b6d9fc0` (PR #37): fresh-context Tester PASS, no open Blocker or Major; report `docs/evidence/TASK-12-13-15-remediation-tester-report.md`. Scheduled Minors listed above remain open.
