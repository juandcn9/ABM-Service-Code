# TASK-06 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only. The Tester did not build TASK-06 and did not use the Builder's tests as the source of checks; checks were derived from the work item acceptance criteria and the cited Specs. Nothing was edited, committed, pushed, or added to refs in the main checkout; the verification ran in a detached worktree that was removed afterwards. Mutants were built in a separate copy.

Revision verified: merge commit `45f388064` (PR #8, `task-06-migrations`, merged on `main`). Worktree HEAD confirmed as `45f388064a13ec4c818ea3aeeab1690e2457b97a`. The head `e461c90` (the reviewed branch head named in the work item) is an ancestor of this merge.

Environment: Windows 11 Home 10.0.26300; venv Python 3.12.10 (`.venv` of the main checkout); SQLite 3.49.1; pytest 9.1.1 with `-p no:cacheprovider`. Specs pin: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.

## Result

PASS with findings (Blocker 0, Major 0, Minor 3).

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| (1) HEAD confirmed | PASS | Worktree at `45f388064a13ec4c818ea3aeeab1690e2457b97a`, clean tracked tree; `e461c90` is an ancestor. |
| (2a) `mypy src harness tests scripts` | PASS (exit 0) | "Success: no issues found in 33 source files". |
| (2b) `pytest -q` | PASS (exit 0) | 300 passed in 20.13 s. |
| (2c) `ruff check .` | PASS (exit 0) | All checks passed. |
| (2d) `ruff format --check .` | PASS (exit 0) | 54 files already formatted. |
| (2e) `scripts/validate_governance.py` | PASS (exit 0) | Required files, Specs pointer v1.0.1 / 5d1cd410, governance headings, workflow pin, placeholders, secret patterns all passed. |
| (3a) `0001` byte identity | PASS | `migrations/0001_initial.sql` SHA-256 `dcf82d06040fac33...73069d02`; `git show 5d1cd41:contracts/sqlite-schema.sql` has the same hash and is byte-identical. |
| (3b) Loader rules | PASS | Probes: gap, duplicate, bad name, uppercase `.SQL`, non-UTF-8, half statement, and `ROLLBACK;` at load time each refused with `MIGRATION_FILES_INVALID`. |
| (3c) Fresh database converges | PASS | Tables `accounts, movements, movement_evidence, holds, ledger_entries, idempotency_outcomes, audit_trace, retention_metadata, schema_version`; `integrity_check` ok and `foreign_key_check` empty; history row `(1, 0001_initial, <checksum>, applied_at)`. |
| (3d) Rerun is a no-op | PASS | Second run keeps the original `applied_at` and adds no row. |
| (3e) Money and immutability constraints | PASS | On a populated ledger row, UPDATE and DELETE of `ledger_entries` refused; UPDATE of `schema_version` refused; currency `EUR`, duplicate `customer_id`, and identifier with a space refused. |
| (3f) Safe errors | PASS | Refusals raise `MigrationError` whose message equals the code only. |
| (3g) Connection state | PASS | Default-isolation connection refused with `MIGRATION_FAILED`; authorizer and progress handler not left installed after a successful run. |
| (4a) Tampered applied migration refused | PASS | Edited `0001` and renamed `0001` both refused with `MIGRATION_CHECKSUM_MISMATCH`; database file SHA-256 unchanged. |
| (4b) Wrong checksum refuses startup | PASS | Trigger blocks a direct UPDATE of history. With the trigger dropped out of band and the checksum changed, startup refuses with `MIGRATION_CHECKSUM_MISMATCH`. |
| (4c) Failing migration rolls back | PASS | Pending 0002 (ok) and 0003 (fails on a missing table): refused with `MIGRATION_FAILED`; neither table exists afterwards; history still only 0001; no transaction left open. |
| (4d) Populated database survives | PASS | Two account rows kept unchanged across an additive 0002; history is `[1, 2]`. |
| (4e) Populated database without history refused | PASS | `UNSUPPORTED_SCHEMA_VERSION`; file bytes unchanged. |
| (4f) Newer database refused | PASS | `UNSUPPORTED_SCHEMA_VERSION`; file bytes unchanged. |

Probe script result: 36 of 38 on the first run. The two failures (ledger UPDATE and DELETE) were defects in the probe itself (the table was empty, so the row triggers had nothing to fire on). Re-run on a populated ledger row: both refused. Not counted as product findings.

## Mutants

Mutants were made from a copy of `src`, `tests`, `harness`, `migrations`, and `pyproject.toml`. Each mutant changed exactly one line or expression in `src/abm/persistence/migrations.py` (the replacement was asserted to match exactly once). Full `pytest` was run from inside each copy.

| Mutant | Change | Result | Caught by (first failures) |
|---|---|---|---|
| M01 | Checksum comparison on applied migrations removed | Killed (2 failed) | `test_edited_applied_migration_is_refused_without_changes`, `test_renamed_applied_migration_is_refused` |
| M02 | Rollback on failure removed | Killed (118 failed) | `test_attacks_on_retained_history_...` cases |
| M03 | Rerun reapplies all migrations (`pending = migrations[:]`) | Killed (17 failed) | `test_legitimate_additive_migrations_still_apply_...`, `test_a_connection_in_a_nonstandard_state_...`, `test_a_fast_migration_is_not_interrupted_...` |
| M04 | Populated database without history adopted (no refusal) | Killed (1 failed) | `test_populated_database_without_history_is_left_untouched` |
| M05 | Newer-than-build database accepted | Killed (1 failed) | `test_database_newer_than_this_build_is_unsupported` |
| M06 | Gap and duplicate check removed | Killed (1 failed) | `test_loader_rejects_gaps_duplicates_and_bad_names` |
| M07 | CRLF normalization removed from checksum | Killed (1 failed) | `test_checksum_ignores_line_ending_style` |
| M08 | Wrong checksum stored on insert (`"0"*64`) | Killed (182 failed) | retained-history attack cases and rerun cases |
| M09 | `BEGIN IMMEDIATE` changed to `BEGIN` | Killed (1 failed) | `test_concurrent_runners_apply_each_migration_exactly_once` (timing-dependent; see Findings) |
| M10 | Pre-COMMIT verification (`_violations`) disabled | Killed (34 failed) | attack cases such as a trigger that deletes ledger rows and a quoted-name forged history insert |
| M11 | Authorizer not installed | Killed (18 failed) | `PRAGMA recursive_triggers`, `trusted_schema`, `query_only` attack cases |

Result: 11 of 11 killed. Each required rule (refuse tampered migration, refuse wrong checksum, no reapply, rollback, populated database survives) has at least one mutant that the suite catches.

Note on the mutant directory: a sibling scratchpad path that was being used for mutants in the same session showed entries I did not create, and `scratchpad/pytest.log` holds output from a different run (572 passed). Results above come only from this run's stdout and from the isolated `t06-mut` directory.

## Findings

Ranked. No Blocker or Major findings.

1. **Minor, Specs drift.** The Specs repository HEAD is now `v1.6.0-2` (`ed6c1ce`), and `contracts/sqlite-schema.sql` there differs from the pinned `v1.0.1` (9 inserted lines since `5d1cd41`). TASK-06 correctly pins `v1.0.1` and `0001` matches it byte for byte, so this is not a defect of this revision. It means the next schema migration must be planned against the current contract, not assumed to match `0001`.
2. **Minor, detection not yet wired.** `retained_history_protected()` is tested directly, but no startup or readiness path calls it in this revision (deferred to TASK-12, as the work item states). Until then, an out-of-band drop of an immutability trigger combined with a row edit is not detected at startup; the runner only compares before and after each migration. Known residual, recorded in the work item.
3. **Minor, timing-dependent kill.** M09 (deferred `BEGIN`) is caught only by the concurrency test, which depends on thread timing. It is not flaky in this run, but it is a single point of detection for the serialization rule.
4. **Minor, record drift.** The work item's local-command counts (275 pytest, 28 mypy files) no longer match `main` (300 pytest, 33 files). Documentation only; the current run is the authoritative count for this revision.

## Not verified

- Multi-process migration race: out of scope per the work item (single-writer baseline; TASK-12). Only the threaded or two-runner test was exercised, and only via the existing test suite.
- CI on the merge commit: not re-run; the CI status is on the PR record, not verified here.
- `retained_history_protected()` on a live readiness path: not wired in this revision (see Finding 2).
- ALTER TABLE, the 12-step table rebuild, and any migration that appends to a retained table: refused by design; not exercised as positive cases.
- The Specs contract changes after `v1.0.1` (Finding 1) were not evaluated against the schema.
- Mutants were not run against a CI environment; Windows and Python 3.12.10 only.
