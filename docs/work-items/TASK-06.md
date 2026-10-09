# Work item: TASK-06 — immutable migrations and schema-version checksum handling

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-06`; `DEC-0007`; `INV-06`, `INV-18`; `DATA-01` through `DATA-08`; `TEST-18` (migration/schema-version part only)
- Decision, gap, or risk records: `DEC-0007`; no new decision or gap; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: implement ordered, immutable, forward-only migrations with a stored SHA-256 checksum per applied version, and ship the approved target schema as migration `0001`.
- Included files/components: `migrations/0001_initial.sql` (byte-for-byte `contracts/sqlite-schema.sql` of Specs `v1.0.1`, SHA-256 `dcf82d06…9d02`); `src/abm/persistence/migrations.py` (loader, checksum, runner, safe `MigrationError` codes); `tests/integration/test_migrations.py`; `.sql` accepted as a governance text suffix; a narrow SQL-scan allowance for the runner.
- Explicit exclusions: connection settings, WAL, busy timeout, transaction unit, repositories and error mapping (`TASK-07`); startup orchestration, the full readiness integrity gate, and FK/registration/trace/reconstruction checks (`TASK-12`, rest of `TEST-18`); the clock port (the caller passes an injected UTC instant); destructive migrations (not permitted in the baseline); backup or restore.
- Dependencies and entry gate: `TASK-03` Verified (Code `aa740bb`); no open GAP.

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_migrations.py`, real SQLite): `0001` equals the contract checksum; the loader orders files and rejects gaps, duplicates, and bad names; an empty database converges to the eight `DATA-01..08` tables plus `schema_version` with a clean `PRAGMA integrity_check` and `foreign_key_check`; rerun is a no-op that keeps the original `applied_at`; pending migrations apply forward in one transaction; an edited or renamed applied migration is refused with `MIGRATION_CHECKSUM_MISMATCH` and no change; a database newer than the build, or a populated database with no history, is refused with `UNSUPPORTED_SCHEMA_VERSION` and left untouched; a failing migration rolls back every pending migration; errors carry only a safe code; the runner requires an autocommit connection and no open transaction; the history table and ledger are immutable by trigger; core money constraints (USD only, positive magnitudes, unique customer/account mapping, identifier alphabet) are enforced by the schema. Mutation checks: removing the rollback or the checksum comparison makes tests fail.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head (pytest, ruff check/format, mypy, toolchain and governance validators), plus the same commands locally.
- Failure, concurrency, authorization, and recovery cases: `BEGIN IMMEDIATE` serializes concurrent migrators and a busy database maps to `MIGRATION_FAILED`; a multi-process race is not tested here (single-writer baseline, `TASK-12` startup).
- Documentation/trace updates: README, CHANGELOG, this work item.

## Implementation notes

- Reversible technical choices: migration name is the file stem (`NNNN_name`, at most 128 characters, stored alphabet); versions must be exactly 1..n; checksums are over LF-normalized UTF-8 so a CRLF checkout keeps them; all pending migrations run in one transaction (specs: one migration transaction), so a failure leaves nothing applied; the runner splits files with `sqlite3.complete_statement` instead of `executescript`, which would commit first; a populated database without `schema_version` is refused rather than adopted.
- `PRAGMA foreign_keys = ON;` in `0001` is kept so the file stays identical to the contract; inside a transaction it is a no-op, so the connection (`TASK-07`) must enable foreign keys itself.
- SQL scan: the runner executes reviewed, checksummed file text, which the fixed-statement rule would reject. `tests/security/test_sql_static_scan.py` lists exactly this one file and waives only that rule for it; value-formatted SQL detection still applies, and a test pins the allowance to this one path.
- The migration files are the single copy of the schema in Code; if the Specs contract changes, a new Specs release and a new migration are required, never an edit of `0001`.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: locally `pytest` 48 passed, `ruff check`, `ruff format --check`, `mypy src tests scripts`, `validate_governance.py`, `validate_toolchain.py` pass; CI results are on the PR.
- Review findings/resolution: Builder Audit `ponytail-review` (installed plugin 5.1.0, `full`, DV-01): one Should-fix, a non-SQLite exception mid-migration would leave the transaction open; fixed by rolling back on any exception, with a test. Independent fresh-context review of head `a545e2e`: PASS with findings (zero Blocker; one process Major, a README/CHANGELOG conflict with `main`). Resolved: `main` merged and the byte-identity check repeated; F1 (a migration could contain `ROLLBACK`/`COMMIT`/`BEGIN` and corrupt the history) now rejected at load time for line-delimited statements and fails closed at apply time for same-line ones; F2 (edge handling inconsistent and raw exceptions such as a path-bearing `PermissionError` escaped) now reports every file problem as `MIGRATION_FILES_INVALID` before any database is touched, accepts only plain lowercase `.sql` files so a mis-cased or stray file cannot hide a version gap, and rejects non-UTF-8 files; F3 (overstated tests) now has tests for a locked database, concurrent runners applying each migration exactly once (removing `BEGIN IMMEDIATE` makes it fail), and ledger, evidence, and audit immutability triggers; F4 (README contradicted itself about the schema) corrected. Observations recorded: the runner does not stop a destructive statement (governance does); the SQL scan waiver is file-wide inside `migrations.py`.
  - Specs observations from the review (contract questions for the Updater, not Code defects): `amount_cents` accepts fractional and numeric-text values because the CHECK range does not require integer type (the application validates integer cents through `Money`); an explicit lower ledger `sequence` can be inserted (monotonicity rests on `AUTOINCREMENT`); `idempotency_outcomes` has no update/delete trigger although DEC-0011 treats stored outcomes as exact; the scope column (128 characters) cannot hold the specified `customer_id + registration` composite, so Code hashes it (see `TASK-10`).
  - A re-review of the fix and Tester verification of the final head are still required.
- Residual risks: schema correctness beyond sampled constraints is only exercised as later tasks use each table; no multi-process migration race test; checksum handling does not defend against someone editing both a migration file and the recorded history together (the history is trigger-protected but SQLite files can be edited directly; readiness in `TASK-12` is the detective control).
- Next safe action: `TASK-07` (connection and transaction unit) after this PR is merged.
