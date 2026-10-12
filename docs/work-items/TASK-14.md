# Work item: TASK-14 — outgoing ACH hold, submission, settlement, rejection, cancellation, and return

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.9.14` / `0cca28b2201ae1785044a246c75c37cd655210da` (current Code pin, `SPEC_VERSION`; Specs origin/main is `v1.9.15` / `0e3b7cacab3142c54f9ba1e24a757ee913ad6d57`, not yet pinned). The TASK-14 rules DEC-0023 and DEC-0024 are present at this pin (`governance/decisions.md`); they first entered at `v1.6.0` / `fa3250e38d04bfc442ee037466a159219092701c`, which is an ancestor of the pin.
- TASK and affected IDs: `TASK-14`; `FR-04`, `FR-05`; `API-07`, `API-08`, `API-09`, `API-10`, `API-11`, `API-22`; `INV-07`, `INV-10`, `INV-15`, `INV-16`; `DATA-02`, `DATA-04`
- Decision, gap, or risk records: `DEC-0017` (destination reference, migration `0002`, Specs PR #8 merged as `1c7213c`); `DEC-0015` and `DEC-0016` (closure); DV-01 closed by `DEC-0020`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: outgoing ACH as six state changes. Acceptance reserves funds with one active hold; submission keeps the hold; settlement posts one debit and posts the hold in the same transaction; rejection and pre-submission cancellation release the hold without a debit; one full return after settlement posts one credit.
- Included files/components: `migrations/0002_movement_destination.sql` (the exact statement in `specs/05` section 8); `src/abm/persistence/migrations.py` (additive `ALTER TABLE` allowed on non-retained tables, verified by a column-layout check; read-only `quick_check` allowed); `src/abm/application/ach.py` (helpers shared with incoming ACH); `src/abm/application/outgoing_ach.py`; `src/abm/application/incoming_ach.py` (switched to the shared helpers, behaviour unchanged); `src/abm/ports/storage.py` and `src/abm/persistence/sqlite_store.py` (holds, restriction, destination); tests `tests/integration/test_outgoing_ach.py`, additions to `tests/integration/test_migrations.py` and `tests/integration/test_migration_protections.py`.
- Explicit exclusions: API routes and envelopes (`TASK-25`); the outgoing-block restriction set and clear (`TASK-20`, the check is in place and tested via the stored restriction); concurrency and fault barriers (`TASK-18`); closure rules for outgoing movements (`TASK-21`).
- Dependencies and entry gate: `TASK-10` and `TASK-11` (merged); Specs pointer `v1.6.0` (Code PR #29 merged).

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_outgoing_ach.py`, real SQLite): acceptance creates one active hold and keeps the balance, with the destination stored; insufficient funds is refused with the outcome stored and nothing else; a restricted or closed account takes no new movement; a duplicate movement id is `INVALID_TRANSITION`; submission keeps the hold active; settlement debits once and posts the hold together; settlement before submission is refused; rejection releases the hold without a debit; cancellation is allowed before submission only; a return posts one full credit after settlement; a return must equal the settled amount and follow settlement; replay of the same key creates no second hold; an injected storage fault during settlement rolls everything back; the database reopens ready after settlement and return.
- Migration: `0002` applies to a database with an existing movement (the column is NULL); the column rejects a malformed value (`test_destination_reference_is_an_additive_nullable_column_of_the_shipped_migrations`).
- Runner: additive `ALTER` passes and `DROP COLUMN`, a table rename, and `ALTER` on a retained table are refused (protection tests).
- Required broader gates: local pytest (561 passed), ruff check and format, mypy `src harness tests scripts`, `validate_governance.py`; `quality-gates` and `validate-governance` on the PR head.
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
- Commands/checks and results: locally `pytest` 561 passed on this branch; `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and `validate_governance.py` pass; CI results are on the PR.
- Review findings/resolution:
  - Fresh-context review of `ddd3002`: FAIL on four Majors. Resolved:
    - Major 1 (duplicate outgoing movement code not declared): JDC option A, DEC-0023 (Specs PR #11, merged); contract API-07 declares `INVALID_TRANSITION`.
    - Major 2 (settlement after an incoming return can leave the balance negative): JDC option B, DEC-0024 (Specs PR #11, merged); INV-10 extended for settlement of a reserved outgoing movement. Test `test_settling_a_reserved_movement_may_leave_the_balance_negative_and_stays_ready`.
    - Major 3 (no test that a hold reduces available funds): `test_an_existing_hold_reduces_the_funds_available_to_a_new_acceptance`; fails when holds are ignored.
    - Major 4 (column-layout check untested): synthetic layout cases and permissive-matrix attacks; fails when the check is disabled.
  - Minor 5 (stale shortcut comment in the migration runner): removed.
  - Open debt, recorded: Minor 6 (verification does not compare constraints of non-retained tables; the real authorizer refuses the rename-and-recreate case); Minor 7 (some refusals come from SQLite's internal statements, not explicit rules); Minor 8 (several migration tests pin to the first migration with `[:1]`, so the shipped 0002 chain is not exercised there); Minor 9 (some assertions are weaker than their names).
  - Merged as PR #22 (merge `a893cc3`, PR head `c8a41d9`). No fresh review or Tester pass on the final head is recorded. The Tester mutation checks above ran on `ddd3002`.
- Mutation checks (Tester, PR #22 head ddd3002): settlement not finalizing the hold: 4 failed; submission finalizing the hold: 3 failed; return skipping the amount check: 1 failed; outgoing create without the funds check: 1 failed; the column-layout check (migration step 7) removed: 0 failed on that head, now killed by 3 tests (the column-change attacks in the permissive matrix and the synthetic layout cases).
- Residual risks: no concurrency test (TASK-18); outgoing restriction is exercised only through the stored value; the migration probe covers a populated database that already holds a movement.
- Next safe action: a fresh review and Tester pass on the merged head `c8a41d9`, recorded before this task is Verified.

## Independent Tester evidence

- Revision: merge `a893cc3`. Report: [`docs/evidence/TASK-14-tester-report.md`](../evidence/TASK-14-tester-report.md).
- Result: PASS with findings: 0 Blocker, 1 Major (pin v1.2.0 lacks DEC-0023 and DEC-0024), 4 Minor. Resolution of the Major: the pin was advanced to `v1.6.0`, which contains DEC-0023 and DEC-0024 and declares API-07 `INVALID_TRANSITION`. No code change was needed. Status stays Implemented; the Minor items and the final-head Tester decision remain open.
