# Work item: TASK-12 — startup migration, integrity, and fail-closed readiness

**Status:** Implemented

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
- Commands/checks and results: locally `pytest` 457 passed in this branch (includes the merged earlier tasks), `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and both validators pass.
- Review findings/resolution: pending (`ponytail-review`, fresh-context review, Tester verification of the final head).
- Residual risks: a very large database makes `PRAGMA integrity_check` slow at startup (acceptable for the single-writer demonstration, `RISK-0001`); the inconsistency queries encode the Builder's reading of `specs/05` section 7 and need a Tester pass against the Specs; readiness is computed on demand, so caching or rate limiting for the health route is a `TASK-25`/`TASK-26` decision.
- Next safe action: `TASK-11` (account reads and trace sequencing), after this PR merges.

## Wiring added before merge

- `readiness_reasons` now calls `retained_history_protected()` (deferred from TASK-06). A guard trigger removed or a retained table altered outside the runner reports `INTEGRITY_FAILED`; the Specs' six reason codes are unchanged. Covered by `test_a_guard_trigger_removed_outside_the_runner_is_not_ready`.
- The direct-corruption test helper drops guard triggers to insert bad rows; that now counts as tampering, so the missing-account case expects `INTEGRITY_FAILED` as well as `FOREIGN_KEY_FAILED`.


## Specs check of the inconsistency queries (Tester, PR #15)

- Matches `specs/05-data-model.md` section 7: projection equals signed ledger sum; holds only for outgoing ACH in `accepted_with_hold|submitted` and card in `authorized_with_hold`, and every such movement has its hold; a hold reserves its own movement's account; no active hold on a closed account; transfer source debits equal destination credits; registration trace and retention row per account; every accepted trace has a committed successful outcome.
- Not yet checked, recorded as open: the explicit available-balance identity (posted minus active held must equal the projection; no separate column exists, so it is implied by the projection check), and the closure and finalized-effects rules, which need data from TASK-13 to TASK-21.
