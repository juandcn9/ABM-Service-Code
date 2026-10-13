# Work item: TASK-12 — startup migration, integrity, and fail-closed readiness

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91` (the version this item was built against; the current Specs pointer is in `README.md`)
- TASK and affected IDs: `TASK-12`; `INV-18`; `NFR-02`; `SEC-10`; `API-20`, `API-21` (the readiness computation only); `TEST-18`; `TEST-30` (direct-corruption half)
- Decision, gap, or risk records: `DEC-0007`; no new decision or gap; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: the startup sequence (open with required settings, apply reviewed forward migrations in one transaction, verify the schema version, run integrity and invariant checks) and a read-only readiness computation that fails closed with controlled reason codes.
- Included files/components: `src/abm/persistence/readiness.py` (`start_database`, `readiness_reasons`, `StartupResult`, the six reason codes) and `tests/integration/test_readiness.py`; the SQL scan waiver now also lists this file for its fixed inconsistency queries.
- Explicit exclusions: the FastAPI `/health/live` and `/health/ready` routes and their JSON bodies (`TASK-25`); configuration parsing and the `CONFIG_INVALID` code, which needs the `ABM_*` settings (`TASK-26`/`TASK-27`); structured logging of failures (`TASK-26`); invariants over tables that later tasks fill (closure rules beyond a closed account holding an active hold, legal-hold consistency) which those tasks add with their data; any repair.
- Dependencies and entry gate: `TASK-06` (migrations) and `TASK-07` (connection), both merged. `TASK-08` to `TASK-10` were merged before the TASK-12 PR was opened, because the tests use registration to build a consistent database.

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_readiness.py`, real SQLite files): an empty volume starts ready with `schema_version` recorded and foreign keys on; a restart on the intact volume stays ready, preserves state, and does not re-apply migrations; a newer schema, a foreign database, and an edited migration are never ready, leave no connection, and report `SCHEMA_UNSUPPORTED`; a garbage file, a missing directory, and a directory path report `DATABASE_UNAVAILABLE`; a locked database reports `DATABASE_BUSY` at startup and for an open connection, and recovers when the lock clears; direct corruption bypassing the immutability triggers makes readiness fail with `INTEGRITY_FAILED` for a projection that differs from the ledger, a ledger entry without its projection, an account without its registration trace or retention row, an accepted trace without its successful idempotency outcome, an active hold on a settled movement, a movement that needs a hold and has none, a transfer with unequal sides, and a closed account with an active hold; an orphan row reports `FOREIGN_KEY_FAILED`; damaged database pages are detected and left exactly as damaged; checks write nothing (a full dump is identical before and after); reason codes are only the controlled set.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head; the SQL static scan covers the new module (fixed statements; waiver pinned to two files by a test).
- Failure, concurrency, authorization, and restart cases: busy, corruption, unsupported schema, and unopenable database are covered; abrupt termination and restart continuity with real traffic belong to `TASK-28`.
- Documentation/trace updates: README, CHANGELOG, this work item.

## Implementation notes

- Reversible technical choices:
  - Readiness returns a sorted list of reason codes (empty means ready). On an unsupported or missing schema it stops at `SCHEMA_UNSUPPORTED` because nothing else can be trusted. Otherwise it runs `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, the twelve inconsistency queries from `specs/05` section 7 (the ten data checks plus two finalized-state checks, see Tester Major M2 below), and a write-lock probe (`BEGIN IMMEDIATE` then `ROLLBACK`, which writes nothing).
  - `start_database` checks that the database parent directory is writable before it opens the file (`specs/07` section 3 step 2). On Windows `os.access` reports only the read-only attribute, so this is a fast path; an unwritable parent that passes it fails at the open step with `DATABASE_UNAVAILABLE`.
  - Any exception outside the migration error path during startup returns `DATABASE_UNAVAILABLE` (or the storage class of a SQLite error) and closes the connection; no exception escapes `start_database`.
  - Driver errors map to codes by their SQLite class: busy gives `DATABASE_BUSY`; corrupt, unreadable, or full storage gives `INTEGRITY_FAILED`; anything else gives `DATABASE_UNAVAILABLE`.
  - The transfer check compares the sum of source debits with the sum of destination credits per transfer, so it assumes nothing about which account column holds which side.
  - `start_database` closes the connection and returns no usable handle whenever the result is not ready.
- Active-hold, transfer, trace, and outcome checks are written against the schema and first saw data from `TASK-13` onward; their tests insert rows directly, so a later task that changes how it records movements must keep these queries true or update them with the Specs.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 were declared deviations DV-01 and DV-02. Both are closed in `docs/governance/deviations.md`: DV-01 by DEC-0020, DV-02 by the TASK-27 container evidence. CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: merged as PR #15 (merge `e996304`); the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: `pytest --collect-only -q -p no:cacheprovider` collects 1291 tests at head `32d9678` (checked 2026-10-12; no `src`, `tests` or `scripts` change since `b122e10`); `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and both validators as recorded at completion.
- Review findings/resolution: fresh-context review of ce8b25d (FAIL: three Majors, all fixed in eb1a4e8); focused re-review of eb1a4e8 PASS with findings (no Blocker or Major); independent Tester pass of eb1a4e8 PASS (CI green on CPython 3.12.15). Gate 8 ponytail-review of the remediation diff returned Ship, with no Must-fix or Should-fix finding; the Ponytail deviation DV-01 is closed by DEC-0020.
- Residual risks: a very large database makes `PRAGMA integrity_check` slow at startup (acceptable for the single-writer demonstration, `RISK-0001`); the inconsistency queries encode the Builder's reading of `specs/05` section 7 and need a Tester pass against the Specs; readiness is computed on demand, so caching or rate limiting for the health route is a `TASK-25`/`TASK-26` decision.
- Next safe action: an independent Tester pass on the current code head naming zero findings. Until then the status stays Implemented (see Status note). The open item is under Scheduled items.

## Wiring added before merge

- `readiness_reasons` now calls `retained_history_protected()` (deferred from TASK-06). A guard trigger removed or a retained table altered outside the runner reports `INTEGRITY_FAILED`; the Specs' six reason codes are unchanged. The object-set check catches a dropped trigger first, so `test_a_guard_trigger_removed_outside_the_runner_is_not_ready` does not exercise this call; `test_a_temp_object_on_the_checked_connection_is_integrity_failed` does.
- The direct-corruption test helper drops guard triggers to insert bad rows; that now counts as tampering, so the missing-account case expects `INTEGRITY_FAILED` as well as `FOREIGN_KEY_FAILED`.

## Specs check of the inconsistency queries (Tester, PR #15)

- Matches `specs/05-data-model.md` section 7: projection equals signed ledger sum; holds only for outgoing ACH in `accepted_with_hold|submitted` and card in `authorized_with_hold`, and every such movement has its hold; a hold reserves its own movement's account; no active hold on a closed account; transfer source debits equal destination credits; registration trace and retention row per account; every accepted trace has a committed successful outcome.
- The open items from this check are recorded once, under Scheduled items below.

## Review fixes (PR #15, fresh-context review of ce8b25d)

- Major 1 (vacuous corruption evidence): the test helper dropped the guard triggers for every case, so the nine data checks were never the reason. `tamper()` now reinstates the guard triggers after the bad rows are written. Removing the inconsistency loop now fails the readiness tests that expect a data-check `INTEGRITY_FAILED`.
- Major 2 (wrong code for a missing object): readiness now compares the set of tables, indexes, views and triggers with the set the reviewed migrations create. A mismatch is `INTEGRITY_FAILED` and stops before the data queries, so a missing table no longer surfaces as `DATABASE_UNAVAILABLE`. Covered by `test_a_missing_table_is_integrity_failed_not_database_unavailable`.
- Major 3 (index checks): the same object comparison covers indexes, so a dropped required index is `INTEGRITY_FAILED` (`test_a_dropped_index_is_integrity_failed`; specs/07 section 3 step 6).
- Minor: the controlled-codes test no longer asserts a string check that could never fail.
- Recorded, not changed: a non-migration exception from `apply_migrations` (or a rollback error) escapes `start_database` without a result; no connection is returned, so it is not fail-open. The static-scan waiver for `readiness.py` is file-wide (the fixed-statement rule); formatted-SQL detection still applies to the file.
- The temp-object check on the readiness connection is covered by `test_a_temp_object_on_the_checked_connection_is_integrity_failed`.

## Independent Tester evidence

- Revision: merge `e996304`. Report: [`docs/evidence/TASK-12-tester-report.md`](../evidence/TASK-12-tester-report.md).
- Result: PASS with findings: 0 Blocker, 1 Major (stored-idempotency JSON check not implemented, Specs 05 s7), 4 Minor. Historical: at that point the status stayed Implemented until the Major findings are resolved.

## Remediation of the Tester Major (2026-10-10)

- Gap closed: readiness now checks that stored idempotency responses are valid JSON (specs/05 s7) before `integrity_check`, and reports `INTEGRITY_FAILED`, not `DATABASE_UNAVAILABLE`. Regression test: `tests/integration/test_readiness.py` (malformed-row case); the test fails without the check. Code commit `43ffbfb` on branch `fix/majors-task-12-13-15`.
- Resolved: the unsupported-schema branch of `readiness_reasons` is tested by `test_readiness_on_a_live_connection_reports_a_newer_schema_as_unsupported` (`tests/integration/test_readiness.py`). Its trigger (TASK-25) has passed; closed by Code PR #41. Owner: Builder (closed).

- Historical Tester record: fresh-context PASS on merged head `b6d9fc0` (PR #37), report `docs/evidence/TASK-12-13-15-remediation-tester-report.md`. Not current: the Stream A Minor closure changed the code on `18fc4e3` after that head, so the status is Implemented (see Status note). The open note in the Specs check section is under Scheduled items.

## Stream A Minor closure (Tester findings of the TASK-12 report)

- Minor 3, reason-code mapping: closed. Owner: Builder (closed). `readiness.py` now applies one documented rule (`_storage_reason`): busy or locked gives `DATABASE_BUSY`; I/O error, corrupt, or full storage gives `INTEGRITY_FAILED`; any other storage error gives `DATABASE_UNAVAILABLE`. The startup path (open and migration causes) and `readiness_reasons` both use it. Tests: `test_each_storage_error_class_maps_to_the_documented_reason_on_readiness` and `test_each_storage_error_class_maps_to_the_documented_reason_at_startup` (nine SQLite classes each; the error carries the SQLite result code), and `test_a_corrupt_database_file_at_startup_is_integrity_failed` (real damaged pages). Before the fix, a corrupt file at startup reported `DATABASE_UNAVAILABLE`.
- Minor 4, hold reserving its own account: closed. Owner: Builder (closed). Test `test_a_hold_reserving_another_accounts_movement_is_integrity_failed` writes a hold on a second, registered account for a movement of the first account, past the guards, and asserts `INTEGRITY_FAILED`.
- Minor 5, non-retained table definitions: closed. Owner: Builder (closed). The object check now compares each stored definition (`sqlite_master.sql`) with the reviewed migrations, not only names. Basis: specs/05 section 8 (the migrated schema is the target) and `contracts/sqlite-schema.sql` (canonical DDL). The migrated `movements` text differs from the contract text only in column order, because section 8 requires `ALTER TABLE ... ADD COLUMN` for releases 1.2.0 and 1.5.0; the reference is therefore the migrated schema. Test `test_a_non_retained_table_definition_changed_out_of_band_is_integrity_failed` alters the `movements` state CHECK through `writable_schema` and asserts `INTEGRITY_FAILED`.
- Mutation evidence (sources put back from SHA-256-verified saved copies): each of five mutants was caught by at least one test: the integrity-code set without 11, the startup cause mapping reverted, the readiness fallback to `DATABASE_UNAVAILABLE`, the cross-account query removed (`test_a_hold_reserving_another_accounts_movement_is_integrity_failed`), and the name-only object comparison (`test_a_non_retained_table_definition_changed_out_of_band_is_integrity_failed`). Per-mutant test counts are not restated, because they were not tied to a head SHA.
- Not in this closure: Minor 2 (the unsupported-schema readiness test) is recorded once, under Remediation above (Resolved, closed by Code PR #41), and is not changed here.

## Status note (Stream A)

- Set to Implemented: the Stream A Minor closure changed this task's code on `18fc4e3`. Verified returns only after an independent Tester pass names the new head and reports zero findings.

## Scheduled items

- Available-balance identity (Tester Major M1): OPEN, blocked on a Specs decision (JDC). `specs/05` section 7 says available (posted minus active held) "must equal the corresponding account projection", while section 4 makes the projection equal to posted. Read literally, every active hold fails readiness. Enabling that check made 32 existing flow and restart tests fail (`test_fault_injection.py`, `test_cards.py` restart cases), so it is not in `readiness.py`. Needed: JDC records the intended identity through the DEC/GAP process; then the check and a corrupted-balance test are added.
- Closure ordering (unchanged): the closure rule is in `readiness.py`, but effects are ordered by timestamp only (the shortcut comment there), so same-second effects are not ordered. Trigger: a stored ledger sequence at closure.
- Finalized-state checks (Tester Major M2): two of the section 5 rules are implemented (see Tester findings below). The predicate is the Builder's reading of `specs/05` section 5, not a Specs-stated query; JDC confirms it through the Specs process. Owner: Builder. Trigger for the rest: TASK-32 (Constitution/Specs conformance and independent review, Draft in `specs/09-delivery-plan.md`).

## Tester findings (branch `fix/task-12-majors`, report head 936d2fa)

- M1 (available-balance identity): not fixed; see Scheduled items. The Specs conflict is recorded there.
- M2 (finalized-state checks): fixed for two rules of `specs/05` section 5. Tests in `tests/integration/test_readiness.py`, direct-corruption cases: "hold-only rejection recorded as a ledger entry" (a ledger entry on a movement in a hold-only terminal state: reversed, expired, rejected, cancelled_before_submission) and "finalized hold citing evidence of another movement" (a finalized hold must cite evidence bound to its own movement). A permitted late clearing after an expired hold is ready: `test_a_late_clearing_after_an_expired_hold_is_ready`. The released-hold rule first flagged a legitimate late clearing, so it was narrowed to terminal movement states.
- m1 (non-retained definition reference): provisional. The reference (migrated schema) follows DEC-0078 option B and GAP-0005's proposed reference. Both are awaiting JDC's decision; the reference is provisional until that decision is recorded.
- m2 (readiness after an additive upgrade): fixed. `test_an_additive_upgrade_from_an_older_schema_is_ready`.
- m3 (mapping coverage): fixed. `test_each_storage_error_class_maps_to_the_documented_reason_at_the_open_step` (the `open_database` cause path) and `test_each_storage_error_class_maps_to_the_documented_reason_at_the_integrity_check` (a failing `PRAGMA integrity_check`), each over the nine SQLite classes.
- m4 (non-migration exception escapes `start_database`): fixed. `start_database` returns `DATABASE_UNAVAILABLE` (or the storage class) and closes the connection. Test: `test_an_unexpected_migration_failure_is_a_controlled_result`.
- m5 (parent-writable check absent): fixed. `start_database` checks `os.access` on the parent before opening. Test: `test_a_read_only_parent_is_unavailable_before_the_database_is_opened` (the check is faked with a monkeypatch, because Windows does not report directory write permission in the usual way).
- m6 (status records disagree): this item stays `Implemented`. The Specs status records (`specs/09`, `status/implementation-status.md`) belong to the Specs repository and are not changed by this branch. A Tester sets `Verified`.
- Mutation evidence: each new test was shown to fail on a deliberate break in `readiness.py`, put back from a SHA-256-verified copy after each break (not by checkout). Breaks and failing tests: release-ledger rule disabled (fails the rejection case); evidence-binding rule disabled (fails the foreign-evidence case); late-clearing rule widened to `late_cleared` (fails the late-clearing test); parent check removed (fails the read-only parent test); generic catch removed (fails the unexpected-failure test); upgrade applies only the first migration (fails the upgrade test among 52 failures); open-step mapping replaced by `DATABASE_UNAVAILABLE` (fails the open-step cases); integrity-step mapping replaced (fails the integrity-step cases).
- Gates: the targeted files (`test_readiness.py`, `test_database.py`, `test_migrations.py`, `test_migration_protections.py`, `test_migration_runner_edges.py`, `tests/unit/test_recovery_claims.py`) and the flow files that restart a database with holds (`test_cards.py`, `test_closure.py`, `test_fault_injection.py`, `test_outgoing_ach.py`, `test_incoming_ach.py`, `test_transfers.py`, `test_http_slice1.py`, `test_http_slice2.py`) pass. The full suite is not run on this host; CI is the place it runs.
