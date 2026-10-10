# Work item: TASK-14 — outgoing ACH hold, submission, settlement, rejection, cancellation, and return

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.2.0` / `32befdaa710404145fa2c13128a8015da761d1f5`
- TASK and affected IDs: `TASK-14`; `FR-04`, `FR-05`; `API-07`, `API-08`, `API-09`, `API-10`, `API-11`, `API-22`; `INV-07`, `INV-10`, `INV-15`, `INV-16`; `DATA-02`, `DATA-04`
- Decision, gap, or risk records: `DEC-0017` (destination reference, migration `0002`, Specs PR #8 merged as `1c7213c`); `DEC-0015` and `DEC-0016` (closure); DV-01 closed by `DEC-0020`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: outgoing ACH as six state changes. Acceptance reserves funds with one active hold; submission keeps the hold; settlement posts one debit and posts the hold in the same transaction; rejection and pre-submission cancellation release the hold without a debit; one full return after settlement posts one credit.
- Included files/components: `migrations/0002_movement_destination.sql` (the exact statement in `specs/05` section 8); `src/abm/persistence/migrations.py` (additive `ALTER TABLE` allowed on non-retained tables, verified by a column-layout check; read-only `quick_check` allowed); `src/abm/application/ach.py` (helpers shared with incoming ACH); `src/abm/application/outgoing_ach.py`; `src/abm/application/incoming_ach.py` (switched to the shared helpers, behaviour unchanged); `src/abm/ports/storage.py` and `src/abm/persistence/sqlite_store.py` (holds, restriction, destination); tests `tests/integration/test_outgoing_ach.py`, additions to `tests/integration/test_migrations.py` and `tests/integration/test_migration_protections.py`.
- Explicit exclusions: API routes and envelopes (`TASK-25`); the outgoing-block restriction set and clear (`TASK-20`, the check is in place and tested via the stored restriction); concurrency and fault barriers (`TASK-18`); closure rules for outgoing movements (`TASK-21`).
- Dependencies and entry gate: `TASK-10` and `TASK-11` (merged); Specs `v1.2.0` pointer (Code PR #21 merged).

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_outgoing_ach.py`, real SQLite): acceptance creates one active hold and keeps the balance, with the destination stored; insufficient funds is refused with the outcome stored and nothing else; a restricted or closed account takes no new movement; a duplicate movement id is `INVALID_TRANSITION`; submission keeps the hold active; settlement debits once and posts the hold together; settlement before submission is refused; rejection releases the hold without a debit; cancellation is allowed before submission only; a return posts one full credit after settlement; a return must equal the settled amount and follow settlement; replay of the same key creates no second hold; an injected storage fault during settlement rolls everything back; the database reopens ready after settlement and return.
- Migration: `0002` applies to a database with an existing movement (the column is NULL); the column rejects a malformed value (`test_destination_reference_is_an_additive_nullable_column_of_the_shipped_migrations`).
- Runner: additive `ALTER` passes and `DROP COLUMN`, a table rename, and `ALTER` on a retained table are refused (protection tests).
- Required broader gates: local pytest (544 passed), ruff check and format, mypy `src harness tests scripts`, `validate_governance.py`; `quality-gates` and `validate-governance` on the PR head.
- Failure and concurrency: a storage fault rolls back (tested); concurrent writers on one movement are not tested here (`TASK-18`).

## Implementation notes

- Each operation is one `run_idempotent` call. Every rejection is decided before the first write. Stored rejections use only codes the contract declares for that operation.
- Movement states: `accepted_with_hold` → `submitted` → `settled` → `returned`; `accepted_with_hold` → `cancelled_before_submission`; `submitted` → `rejected`. Settled may return once.
- Holds: one per movement (`holds.movement_id` is unique). Submission leaves it `active`; settlement sets it `posted` with the settlement evidence; rejection and cancellation set it `released`. Available balance is derived (current minus active holds), so it is never stored.
- Ledger effects: `outgoing_settlement` (debit) and `outgoing_return` (credit). The ledger id is a SHA-256 of the movement and effect.
- Builder decisions for review:
  - Submission, settlement, rejection and cancellation do not check `ACCOUNT_CLOSED`: closure requires no unresolved movement (INV-15), so these cannot occur on a closed account, and the contract declares no such code for them.
  - A return on a closed account is accepted, as for incoming ACH (INV-16, DEC-0015).
  - Duplicate movement id on create is `INVALID_TRANSITION` (DEC-0014 pattern).
  - Restriction is checked on create only (`OUTGOING_BLOCKED`); the restriction is set by `TASK-20`.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are recorded (DEC-0020 closes DV-01); CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: locally `pytest` 544 passed on this branch; `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and `validate_governance.py` pass; CI results are on the PR.
- Review findings/resolution: pending (fresh-context review and Tester verification of the final head).
- Residual risks: the mutation check for TASK-14 is not yet recorded; no concurrency test (TASK-18); outgoing restriction is exercised only through the stored value.
- Next safe action: review and Tester of the final head, then the PR is ready for JDC merge; `TASK-15` (internal transfer) after this PR merges, under the one-task rule.
