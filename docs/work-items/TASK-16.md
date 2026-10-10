# Work item: TASK-16 — card authorization, clearing, reversal, expiry, late clearing, and refund

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.5.0` / `9886e96060560ae8a168a80c2d91d1f4c15105bb`
- TASK and affected IDs: `TASK-16`; `FR-07`, `FR-08`; `API-13`, `API-14`, `API-15`, `API-23`, `API-24`; `INV-07`, `INV-10`; `DATA-02`, `DATA-04`
- Decision, gap, or risk records: `DEC-0026` (reused movement id is `INVALID_TRANSITION`, declared on API-13), `DEC-0027` (`merchant_reference` column, migration `0003`)
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: card lifecycle as five state changes. Authorization reserves funds with one hold. Clearing posts an evidence-backed debit and posts the hold (the final amount may differ). Reversal and expiry release the hold without posting. A late clearing after reversal or expiry posts one debit without a hold and never reopens an account. One full refund equal to the clearing debit follows clearing.
- Included files/components: `migrations/0003_card_and_correction_references.sql` (the two statements of `specs/05` s8, byte-for-byte); `src/abm/application/cards.py`; `src/abm/ports/storage.py` and `src/abm/persistence/sqlite_store.py` (merchant reference on new movements; ledger amount lookup); `tests/integration/test_cards.py`; the shipped-migration name list in `tests/integration/test_migrations.py`.
- Explicit exclusions: API routes (`TASK-25`); `decision_reference` use (corrections, `TASK-19`); concurrency (`TASK-18`).
- Dependencies and entry gate: `TASK-10`, `TASK-11`, `TASK-14`; Specs `v1.5.0` (pointer PR #26).

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_cards.py`, real SQLite): authorization holds the funds and stores the merchant reference; insufficient funds and a blocked account are refused; a reused movement id is `INVALID_TRANSITION`; clearing at the authorized amount releases the hold and posts one debit; clearing may differ from the authorized amount and may leave the balance negative, and the database reopens ready; reversal and expiry release the hold without posting; a late clearing after reversal posts one debit with no hold; a late clearing is accepted after closure and does not reopen the account; a cleared movement cannot be cleared again or reversed; a full refund posts one credit; a partial refund and a refund before clearing are refused; a caller without the role is refused before any write; a replay returns the stored outcome; a storage fault during clearing rolls back everything.
- Mutation checks (scratch, exact text): removing the reversal's hold release fails 3 tests; removing the refund amount check fails 1 test.
- Migration `0003`: its statements match `specs/05` s8 exactly; the shipped-migration list includes it.
- Required gates: local pytest (587 passed), ruff check and format, mypy `src harness tests scripts`, `validate_governance.py`; `quality-gates` and `validate-governance` on the PR head.

## Implementation notes

- Movement states: `authorized_with_hold` → `cleared`, `reversed`, or `expired`; `reversed` or `expired` → `late_cleared`; `cleared` or `late_cleared` → `refunded`.
- Holds: one per authorization. Clearing from an authorization posts the hold; reversal and expiry release it. A late clearing has no hold.
- Ledger effects: `card_clearing` (debit, the clearing amount) and `card_refund` (credit). The refund must equal the clearing debit (`AMOUNT_MISMATCH`).
- Decisions applied: the reused movement id is `INVALID_TRANSITION` (DEC-0026); `merchant_reference` is stored (DEC-0027).
- Clearing does not check `ACCOUNT_CLOSED`: specs/02 permits late clearing after closure, and the contract declares no such code for API-14.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: locally `pytest` 587 passed on this branch; `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, `validate_governance.py` pass.
- Review findings/resolution: fresh-context review of the final head `8827002`: no Blocker or Major. Its one Major, the missing cross-account test, was closed in `d2670de` and confirmed by a mutant. Targeted Tester re-check of `92dc02f`: PASS, no Blocker or Major (mypy, pytest 590, ruff all pass). Merged as PR #27 at `ee096fd` on head `8827002`. Minor findings are listed in the Specs status file. The committed report is [`docs/evidence/TASK-16-tester-report.md`](../evidence/TASK-16-tester-report.md).
- Residual risks: no concurrency test (TASK-18); the card path is not exercised over HTTP (TASK-25).
- Next safe action: none for TASK-16 (Verified, DEC-0038). Its scheduled items are in the lines below.

## Verification (2026-10-10, JDC decision, recorded as DEC-0038 in Specs)

- JDC decided TASK-16 is Verified on merged head `0ce8071` (PR #43), on the Tester pass in `docs/evidence/TASK-16-tester-report-2.md` (PR #44). The decision is recorded in the Specs repository as DEC-0038.
- The Minors listed in PR #41 remain open and scheduled; they do not block this status.
- Closed after Verified, by PR #48: fingerprint replay and conflict for authorize, clear and refund; response balances after authorize, clear, reverse and refund; full counts in the reused-id test; the restriction UPDATE names its account.
- Scheduled (owner Builder, trigger TASK-21, closure): the closed-account card cases that set closure by direct SQL.
