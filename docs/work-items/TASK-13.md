# Work item: TASK-13 — incoming ACH notice, settlement, and return

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-13`; `FR-02`, `FR-03`; `API-04`, `API-05`, `API-06`; `INV-10`; `INV-07`; `INV-15`; `DATA-02`, `DATA-04`
- Closed-account and duplicate-movement rules: `DEC-0014` and `DEC-0015` (Specs PR #5 and #6, approved) in `governance/decisions.md`; not in the `v1.0.1` text above. Present at Specs `v1.6.0` and later, including the current pin `v1.9.13` / `fb32e092b7bab696c0dcad7ef76eb7ef7fa08c65`.
- Decision, gap, or risk records: `DEC-0014`, `DEC-0015` (Specs); the Builder choices below are recorded here for review; DV-01 and DV-02 in `docs/governance/deviations.md`
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
  - Settlement on a closed account is refused as `ACCOUNT_CLOSED` (422); a return on a closed account is accepted (`DEC-0015`, INV-16). Revisit with `TASK-21`.
  - A reused evidence reference is refused as `INVALID_TRANSITION` (409).
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: locally `pytest` 523 passed on this branch; `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and `validate_governance.py` pass; CI results are on the PR.
- Review findings/resolution: fresh-context review of 0cd1f1d PASS with findings; Tester of 0cd1f1d PASS (no Blocker or Major).
  - Fixed: settlement trace and closed-account settle and return now tested; reopen asserts the trace outcome; the authorization test proves denial happens before any storage access; one cents bound (shared with the domain).
  - Decided by JDC (contract change, Specs PR #5, awaiting approval):
    1. Duplicate `movement_id` on create is `INVALID_TRANSITION` (409). The Specs PR declares it on create and lists it as stored.
    2. Settlement on a closed account is `ACCOUNT_CLOSED` (422), declared on settlement. A return on a closed account is accepted, as INV-16 permits; `specs/04` section 3.1 now lists API-06 accordingly.
    This PR stays draft until Specs PR #5 is approved, so the contract and the code agree.
  - Recorded, not fixed: a credit past the schema's cents bound becomes `INTERNAL_ERROR` (no defined rejection); `external_reference` is not unique (the Specs wording 'new movement/reference' is ambiguous).
- Residual risks: the closed-account rule for incoming evidence is a Builder decision (see above); no outgoing debit yet, so the negative-balance return path is untested.
- Next safe action: `TASK-14` (outgoing ACH) and `TASK-15` (transfer) after this PR merges, under the one-task rule.

## Independent Tester evidence

- Revision: merge `487be1f`. Report: [`docs/evidence/TASK-13-tester-report.md`](../evidence/TASK-13-tester-report.md).
- Result: PASS with findings: 0 Blocker, 2 Major (pinned Specs lacks the rules implemented; no cross-account test), 5 Minor. Status stays Implemented until the Major findings are resolved.

## Remediation of the Tester Majors (2026-10-10)

- F2 closed: tests `test_another_accounts_movement_is_not_found_for_settlement_or_return` in `tests/integration/test_incoming_ach.py` cover settlement and return through another account's id (MOVEMENT_NOT_FOUND, no write). Each owner-check mutant fails the test. Code commit `43ffbfb`.
- F1 (traceability) fixed: the rules the Tester found missing from the pinned v1.0.1 (closed-account return, duplicate movement) are approved in `DEC-0014` and `DEC-0015` (Specs PR #5 and #6), present at `v1.6.0` and later. The Authority section now cites them; the Code pin is `v1.9.13` / `fb32e092b7bab696c0dcad7ef76eb7ef7fa08c65` (`SPEC_VERSION`). The earlier "v1.7.0 (eb345c8)" reference was wrong: `eb345c8` is not a commit in the Specs repository.
- The Completion item on Specs PR #5 "awaiting approval" is superseded: `DEC-0014` and `DEC-0015` are approved.
