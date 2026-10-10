# Work item: TASK-15 — atomic internal transfer

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.3.0` / `8250d21d5c800a31f5dab4bdd1a31bfeb396a056`
- TASK and affected IDs: `TASK-15`; `FR-06`; `API-12`; `INV-07`, `INV-10`; `DATA-02`, `DATA-04`
- Decision, gap, or risk records: DEC-0025 (a reused movement id is `INVALID_TRANSITION`, declared on API-12, JDC option A)
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: one atomic transfer between two open accounts: the source is debited and the destination credited by the same integer amount in one write transaction, completing the movement immediately.
- Included files/components: `src/abm/application/transfers.py` (`internal_transfer`); `src/abm/ports/storage.py` and `src/abm/persistence/sqlite_store.py` (movement counterparty account); `tests/integration/test_transfers.py`.
- Explicit exclusions: API routes and envelopes (`TASK-25`); cross-process concurrency (`TASK-18`).
- Dependencies and entry gate: `TASK-10` and `TASK-11` (merged); `TASK-14` (merged).

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_transfers.py`, real SQLite): a transfer moves equal amounts in one completed movement with two equal ledger effects and a trace entry; insufficient funds is refused with only the outcome stored; a hold on the source reduces what can be transferred; a restricted source and a closed account take no transfer; an unknown account is not found and the same account is refused as a validation error; a caller without the role is refused before any write; a replay returns the stored outcome and a changed request conflicts; an injected storage fault on the destination rolls everything back; the database reopens ready with the balances intact.
- Required broader gates: local pytest (570 passed), ruff check and format, mypy `src harness tests scripts`, `validate_governance.py`; `quality-gates` and `validate-governance` on the PR head.

## Implementation notes

- Movement `internal_transfer`, state `completed`, source as `account_id` and destination as `counterparty_account_id` (schema check: the two differ).
- Ledger effects: `transfer_source_debit` (debit, source) and `transfer_destination_credit` (credit, destination), ids derived from the movement.
- The source must be unrestricted and have available funds (current minus active holds); the destination only needs to be open.
- Builder decisions for review:
  - Same source and destination is `VALIDATION_ERROR` (400), not stored, because the contract declares no code for it on this operation.
  - A reused movement id is `INVALID_TRANSITION`, declared on API-12 by DEC-0025 (Specs v1.3.0 plus DEC-0025).
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are recorded; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: locally `pytest` 572 passed on this branch; `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, `validate_governance.py` pass.
- Review findings/resolution: pending (fresh-context review and Tester verification of the final head).
- Residual risks: no concurrency test (TASK-18).
- Next safe action: TASK-15 is merged (PR #24). Record its fresh review and Tester pass before it is Verified. No such record exists yet.

## Review fixes (PR #24)

- Duplicate movement id: `INVALID_TRANSITION` is now declared on API-12 by DEC-0025 (Specs v1.3.0 plus DEC-0025). Test `test_a_reused_movement_id_under_a_new_key_is_invalid_transition`; removing the check fails it.
- Destination credit: one trace row per ledger effect (the source debit and the destination credit), so reconciliation sees both ledger IDs. Test `test_both_ledger_effects_appear_in_the_trace`. Builder choice; reversible.
- Insufficient funds: the test now asserts the stored outcome row.
- Pin: the branch merges `main` after PR #23, so the work item's `v1.3.0` pin is the code's pin.
