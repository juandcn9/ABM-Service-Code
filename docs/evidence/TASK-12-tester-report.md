# TASK-12 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only. The Tester did not build TASK-12. Work was done in a detached worktree at the revision below; the main checkout was not edited, committed, or pushed, and git config was not changed.

Revision verified: merge commit `e9963049f` (PR #15, `task-12-readiness`, merged on `main`). HEAD of the worktree confirmed as `e9963049fa91ce88ff4ac7e8b9952e56e5d9c530`. Work item: `docs/work-items/TASK-12.md` at that commit.

Environment: Windows 11 Home 10.0.26300; project venv Python 3.12.10 (CI pins 3.12.15, not re-run); Specs v1.0.1, commit `5d1cd410399a6fb0154a0117728c409cc7f2ec91` (from `SPEC_VERSION`); Specs read from the local Specs checkout at commit `ed6c1ce2c2ea03860e369a1aa6fa4c6e57c0f28a` (read only).

## Result

PASS with findings: 0 Blocker, 1 Major, 4 Minor. All gates pass and every fail-closed path attacked returns a non-ready result; the findings concern Specs coverage, test coverage, and reason-code mapping, not a fail-open path.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| HEAD confirmed | PASS | `e9963049f` (worktree detached at merge commit) |
| `mypy src harness tests scripts` | PASS (exit 0) | Success: no issues found in 43 source files |
| `pytest -q -p no:cacheprovider` | PASS (exit 0) | 460 passed (matches the work item count); pytest `pythonpath` resolves to the worktree `src` |
| `ruff check .` | PASS (exit 0) | All checks passed |
| `ruff format --check .` | PASS (exit 0) | 68 files already formatted |
| `scripts/validate_governance.py` | PASS (exit 0) | 11 required files; Specs pointer v1.0.1 / 5d1cd41; headings, pin, placeholders, secret patterns passed |
| Empty volume starts ready, `schema_version` = 1, FK on | PASS | `test_empty_volume_starts_ready_and_records_the_schema_version` |
| Restart keeps state, no re-apply | PASS | `applied_at` unchanged on restart |
| Newer / foreign / edited schema: `SCHEMA_UNSUPPORTED`, no connection | PASS via `start_database` | Parametrized test passes; the `readiness_reasons` branch is not directly covered (F2) |
| Garbage file, missing directory, directory path: `DATABASE_UNAVAILABLE` | PASS | Test passes |
| Busy at startup and busy with an open connection: `DATABASE_BUSY`, recovers when lock clears | PASS | Both busy tests pass; the open-connection case is mutant-sensitive (M3, M6) |
| Direct corruption of each data invariant: `INTEGRITY_FAILED` | PASS | 9 parametrized cases pass; each one is reached only by its own data check (guards restored after tampering) |
| Orphan row: `FOREIGN_KEY_FAILED` | PASS | Missing-account case passes (M2 caught) |
| Missing table / dropped index: `INTEGRITY_FAILED` | PASS | Object-set tests pass (M8 caught) |
| Page-level file damage detected, bytes not repaired | PASS | `test_file_level_corruption_is_detected_and_never_repaired` passes; reason is `DATABASE_UNAVAILABLE` (F3) |
| Checks write nothing (full dump identical) | PASS | `test_readiness_checks_write_nothing` passes |
| Reason codes limited to the controlled set | PASS | `test_reason_codes_are_controlled_values_only` passes; F1 and F3 show codes returned by error paths are not always the intended ones |
| Specs 05 section 7: nine inconsistency queries | PARTIAL | Eight of the listed items are implemented; the stored-idempotency JSON check is absent (F1); the hold-reserves-own-account query is untested (F4) |
| Specs 07 section 3 step 5 (schema version equals supported) and step 6 (integrity, FK, invariants, required indexes) | PASS | Implemented via `_schema_supported`, integrity, FK, inconsistency, and object-set checks |
| Specs 05 section 7 / 07 section 4 for non-retained table definitions | PARTIAL | Object names only; out-of-band definition edit is not detected (F5) |
| Probes (throwaway databases in the scratch area, not the worktree) | See Findings | P1 newer row after startup: `SCHEMA_UNSUPPORTED` (correct); P2 foreign table: `INTEGRITY_FAILED`; P3 CHECK removed on `movements` via writable_schema: ready (F5); P4 corrupt page at startup: `DATABASE_UNAVAILABLE` (F3); P5 invalid stored JSON: `DATABASE_UNAVAILABLE` (F1, F3) |

## Mutants

Built in a self-contained copy (`src`, `tests`, `harness`, `migrations`, `pyproject.toml`); each mutant changed only `src/abm/persistence/readiness.py` (exact-match replacement asserted); pytest run from inside the copy against `tests/integration/test_readiness.py`. Baseline copy: 26 passed.

| ID | Mutation | Result | Caught by |
|---|---|---|---|
| M1 | `_schema_supported` check bypassed in `readiness_reasons` | SURVIVED (26 passed) | Not caught; unsupported-schema tests go through `start_database`, which rejects earlier (F2) |
| M2 | `PRAGMA foreign_key_check` branch removed | Caught (1 failed) | Missing-account FK case |
| M3 | `_can_begin_write` probe skipped | Caught (1 failed) | `test_readiness_reports_busy_for_an_already_open_connection` |
| M4 | Transfer source/destination query disabled | Caught (1 failed) | Transfer-unequal-sides case |
| M5 | `start_database` returns connection despite reasons | Caught (1 failed) | `test_file_level_corruption_is_detected_and_never_repaired` |
| M6 | Busy probe mapped to `INTEGRITY_FAILED` | Caught (1 failed) | Open-connection busy test |
| M7 | `retained_history_protected` call removed | Caught (1 failed) | `test_a_temp_object_on_the_checked_connection_is_integrity_failed` |
| M8 | Object-set comparison bypassed | Caught (2 failed) | Missing-table and dropped-index tests |
| M9 | Hold-reserves-own-account query disabled | SURVIVED (26 passed) | Not caught; no test covers that query (F4) |

Result: 7 of 9 mutants caught; 2 survived (M1, M9).

## Findings

Ranked, highest first.

1. **Major: stored idempotency JSON check missing; invalid JSON gives the wrong code.** Specs 05 section 7 lists "stored idempotency JSON/outcomes" among readiness checks. `readiness_reasons` has no JSON validity query, and the work item's open-items list does not record this gap. Probe: a row with `response_json = '{not json'`, inserted with `ignore_check_constraints` on, returns `DATABASE_UNAVAILABLE` (SQLite raises "malformed JSON" from `PRAGMA integrity_check`, which the error map treats as a generic error). The result is still not ready (fail-closed holds), but the specified check is not implemented and the code is wrong. Suggested fix: add a `json_valid` inconsistency query, map this case to `INTEGRITY_FAILED`, add a test, and record the gap in the work item and Specs trace.

2. **Minor: unsupported-schema branch of `readiness_reasons` has no test.** Mutant M1 survives. Probe P1 shows the real function does return `SCHEMA_UNSUPPORTED` when a newer `schema_version` row appears after startup, so behavior is correct today. The gap matters because TASK-25 will compute readiness on demand. Suggested fix: a test that calls `readiness_reasons` directly on a database with an extra history row or a foreign history.

3. **Minor: reason-code mapping differs from the documented rule.** The work item states that corrupt, unreadable, or full storage gives `INTEGRITY_FAILED` and other driver errors give `DATABASE_UNAVAILABLE`. On the startup path, any `apply_migrations` failure that is not busy becomes `MIGRATION_FAILED`, which `start_database` maps to `DATABASE_UNAVAILABLE` regardless of cause (probe P4: a corrupted page at startup gives `DATABASE_UNAVAILABLE`). The same occurs in `readiness_reasons` for generic SQLite errors (F1). Fail-closed is unaffected; operator-facing codes are misleading.

4. **Minor: hold-reserves-own-account query untested.** The query `h.account_id <> m.account_id` (a Builder addition, not in the Specs 05 section 7 text) has no test that exercises it; mutant M9 survives. Suggested fix: a direct-corruption case with a hold on a different account than its movement.

5. **Minor: non-retained table definitions are not verified.** The object check compares names only. Probe P3 removed the `state` CHECK from `movements` through `writable_schema` (out-of-band) and `start_database` and `readiness_reasons` both reported ready; a bogus state was accepted. Specs 07 section 4 says "required objects exist", so this is within the letter of the Specs, but a deliberate out-of-band definition change is not detected. Consider comparing `sqlite_master.sql` for all shipped objects, or record it as an accepted risk in `decisions.md`.

## Not verified

- CI on CPython 3.12.15 and the PR #15 CI run; only the local 3.12.10 venv was used.
- `ponytail-review` was not run (declared deviation DV-01); this is a Tester pass, not a code review.
- Multi-process concurrency and real traffic; busy tests use one process and explicit locks. Abrupt-termination recovery belongs to TASK-28.
- Startup steps 1 and 2 of specs/07 section 3 (configuration parsing and writable-parent check) and `CONFIG_INVALID`: outside TASK-12 scope per the work item exclusions.
- Finalized-effects and closure rules beyond the closed-account hold check, and the explicit available-balance identity: recorded as open in the work item (TASK-13 to TASK-21).
- Performance of `PRAGMA integrity_check` on a large database (RISK-0001).
- Non-Windows platforms.
- Mutants were run only in the copy; the main checkout and the Specs repo were not modified.
