# Work item: TASK-13 — incoming ACH notice, settlement, and return

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-13`; `FR-02`, `FR-03`; `API-04`, `API-05`, `API-06`; `INV-10`; `INV-07`; `INV-15`; `DATA-02`, `DATA-04`
- Decision, gap, or risk records: none new; the decisions below are Builder choices recorded here for review; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: incoming ACH as three state changes: a notice creates a pending movement with no balance effect; valid settlement evidence posts one credit and settles the movement; one full return equal to that credit posts one debit and returns the movement.
- Included files/components: `src/abm/application/incoming_ach.py` (`create_incoming_ach`, `settle_incoming_ach`, `return_incoming_ach`); `src/abm/ports/storage.py` (movement, evidence, ledger and balance methods on the write port); `src/abm/persistence/sqlite_store.py` (their SQL); `tests/integration/test_incoming_ach.py`.
- Explicit exclusions: the FastAPI routes and envelopes (`TASK-25`); outgoing ACH, transfers, and cards (`TASK-14` to `TASK-16`); cross-process concurrency and fault barriers (`TASK-18`); the evidence-to-trace rule for the write paths beyond what is stored here.
- Dependencies and entry gate: `TASK-10` (idempotency runner, registration) and `TASK-11` (reads), both merged to `main`.

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_incoming_ach.py`, real SQLite): a notice creates one pending movement with no ledger row and no balance change; settlement posts one credit, settles, and records the evidence and trace; a return posts one full debit and returns the movement; the same key and request replays with no second effect; a changed request under the same key conflicts and changes nothing; a second settlement and a second return are refused with `INVALID_TRANSITION`; an evidence reference cannot be reused for another movement; a return before settlement is refused; a return that differs from the settled amount is refused with `AMOUNT_MISMATCH`; an unknown movement or account is not found; a closed account takes no new movement; a caller without the role is refused before any write; invalid amounts are refused with nothing stored; an injected storage fault mid-settlement rolls back every effect; after a full lifecycle the database reopens ready (projection equals ledger, trace has a successful outcome).
- Required broader gates: local pytest, ruff, format, mypy, both validators; `validate-governance` and `quality-gates` on the PR head.
- Failure and concurrency: a storage fault rolls back (tested); concurrent writers on one movement are not tested here (`TASK-18`).

## Implementation notes

- Each state change is one `run_idempotent` call. Every rejection is decided before the first write, and the storable ones (the nine codes the outcome table allows) are stored as deterministic outcomes.
- Movement states used: `pending` → `settled` → `returned`, matching `specs/02` (incoming ACH). Settled is reached once and returned once.
- Ledger effects: `incoming_settlement` (credit) and `incoming_return` (debit). The ledger id is a SHA-256 of the movement and effect, so each effect exists once per movement.
- The return may take the balance negative (INV-10). No test drives the balance negative yet; that needs an outgoing debit (`TASK-14`).
- Builder decisions for review:
  - A duplicate `movement_id` is refused as `INVALID_TRANSITION` (409). The Specs name no duplicate-movement code.
  - Settlement and return on a closed account are refused as `ACCOUNT_CLOSED` (422). The Specs allow only defined late evidence after closure; whether incoming settlement or return is such evidence belongs to `TASK-21`, and this choice must be revisited there.
  - A reused evidence reference is refused as `INVALID_TRANSITION` (409).
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: locally `pytest` 523 passed on this branch; `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and `validate_governance.py` pass; CI results are on the PR.
- Review findings/resolution: pending (fresh-context review and Tester verification of the final head).
- Residual risks: the closed-account rule for incoming evidence is a Builder decision (see above); no outgoing debit yet, so the negative-balance return path is untested.
- Next safe action: `TASK-14` (outgoing ACH) and `TASK-15` (transfer) after this PR merges, under the one-task rule.
