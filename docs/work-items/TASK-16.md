# Work item: TASK-16 — card authorization, clearing, reversal, expiry, late clearing, and refund

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.5.0` / `9886e96060560ae8a168a80c2d91d1f4c15105bb` (the version this item was built against; the current Specs pointer is in `README.md`)
- TASK and affected IDs: `TASK-16`; `FR-07`, `FR-08`; `API-13`, `API-14`, `API-15`, `API-23`, `API-24`; `INV-07`, `INV-10`; `DATA-02`, `DATA-04`
- Decision, gap, or risk records: `DEC-0026` (reused movement id is `INVALID_TRANSITION`, declared on API-13), `DEC-0027` (`merchant_reference` column, migration `0003`), `DEC-0038` (Specs; the Verified status it records is superseded for the current head, see Status decision)
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required. Status decisions: JDC.

## Scope

- Objective: card lifecycle as five state changes. Authorization reserves funds with one hold. Clearing posts an evidence-backed debit and posts the hold (the final amount may differ). Reversal and expiry release the hold without posting. A late clearing after reversal or expiry posts one debit without a hold and never changes a closed account's state. One full refund equal to the clearing debit follows clearing.
- Included files/components: `migrations/0003_card_and_correction_references.sql` (the two statements of `specs/05` s8, byte-for-byte); `src/abm/application/cards.py`; `src/abm/ports/storage.py` and `src/abm/persistence/sqlite_store.py` (merchant reference on new movements; ledger amount lookup); `tests/integration/test_cards.py`; the shipped-migration name list in `tests/integration/test_migrations.py`.
- Explicit exclusions: API routes (`TASK-25`); `decision_reference` use (corrections, `TASK-19`); concurrency (`TASK-18`).
- Dependencies and entry gate: `TASK-10`, `TASK-11`, `TASK-14`; Specs `v1.5.0` (pointer PR #26).

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_cards.py`, real SQLite): authorization holds the funds and stores the merchant reference; insufficient funds and a blocked account are refused; a reused movement id is `INVALID_TRANSITION`; clearing at the authorized amount releases the hold and posts one debit; clearing may differ from the authorized amount and may leave the balance negative, and the database is ready again; reversal and expiry release the hold without posting; a late clearing after reversal posts one debit with no hold; a late clearing is accepted after closure and does not change the account's state; a cleared movement cannot be cleared again or reversed; a full refund posts one credit; a partial refund and a refund before clearing are refused; a caller without the role is refused before any write; a replay returns the stored outcome; a storage fault during clearing leaves no partial effect.
- Mutation checks (scratch, exact text): removing the reversal's hold release and removing the refund amount check were each killed by the focused tests at the verified head `0ce8071` (DEC-0038: all four mutants killed). Per-mutant counts are not restated, because they were not tied to a head SHA.
- Migration `0003`: its statements match `specs/05` s8 exactly; the shipped-migration list includes it.
- Required gates at the verified head `0ce8071`: local pytest, ruff check and format, mypy `src harness tests scripts`, `validate_governance.py`; `quality-gates` and `validate-governance` on the PR head (recorded in DEC-0038). At the current code head `b733389` (2026-10-13, branch `fix/task-16-minors`; includes PR #48 and the Tester Minor fixes): `pytest --collect-only -q -p no:cacheprovider` collects 1293 tests. Targeted runs (`tests/integration/test_cards.py`, `test_closure.py`, `test_risk_restriction.py`, `tests/security/test_block_resolution.py`) pass with 62 tests. The full pytest run was not executed on the review host; the head-level gates for `b733389` are not claimed beyond the collection and the checks listed under Completion.

## Implementation notes

- Movement states: `authorized_with_hold` → `cleared`, `reversed`, or `expired`; `reversed` or `expired` → `late_cleared`; `cleared` or `late_cleared` → `refunded`.
- Holds: one per authorization. Clearing from an authorization posts the hold; reversal and expiry release it. A late clearing has no hold.
- Ledger effects: `card_clearing` (debit, the clearing amount) and `card_refund` (credit). The refund must equal the clearing debit (`AMOUNT_MISMATCH`).
- Decisions applied: the reused movement id is `INVALID_TRANSITION` (DEC-0026); `merchant_reference` is stored (DEC-0027).
- Clearing does not check `ACCOUNT_CLOSED`: specs/02 permits late clearing after closure, and the contract declares no such code for API-14.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: as recorded at the verified head `0ce8071` (local pytest, `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and `validate_governance.py` pass; see Acceptance evidence). At head `b733389`: 1293 tests collected (`pytest --collect-only -q -p no:cacheprovider`, 2026-10-13).
- Review findings/resolution: fresh-context review of the final head `8827002` found one Major, the missing cross-account test, was closed in `d2670de` and confirmed by a mutant. Targeted Tester re-check of `92dc02f`: PASS, no Blocker or Major (mypy, pytest and ruff all pass). Merged as PR #27 at `ee096fd` on head `8827002`. Minor findings are under the Minor closure section. The committed report is [`docs/evidence/TASK-16-tester-report.md`](../evidence/TASK-16-tester-report.md).
- Residual risks: no concurrency test (TASK-18); the card path is not exercised over HTTP (TASK-25).
- Next safe action: an independent Tester pass on the current head `b733389` naming zero findings; then a new JDC decision on the Verified status (see Status decision). The open decision is under Open decision; the scheduled items are under Scheduled items.

## Status decision (2026-10-12, owner JDC)

- Status is Implemented. The Verified statement recorded for `0ce8071` does not cover the current head `b733389`: PR #48 (merge `aeb3b2b`) changed `tests/integration/test_cards.py` after `0ce8071`, and no Tester pass covers that change.
- The Specs repository still records TASK-16 as Verified (DEC-0038, and the TASK-16 status cell under DEC-0039). Changing that Specs status needs a new JDC decision; this file does not make it.
- Reinstating Verified needs an independent Tester pass on the head named in the record, with zero Blocker or Major findings, and a new JDC decision.

## Open decision (owner JDC)

- Closed-account card tests: TASK-21 kept the closed-account card tests that set closure by direct SQL, by design, so the trigger passed without closing this item. Still direct SQL: `test_authorization_on_a_closed_account_is_refused_and_writes_nothing` and related cases in `tests/integration/test_cards.py`. DEC-0039 schedules these to TASK-21 (closure) and does not close them. Decide whether direct-SQL closure setup stays the test pattern, or the tests must use the real closure command. Trigger: this JDC decision.

## Minor closure (Tester findings of `936d2fa`)

- Closed, with tests: refund over the `late_cleared` amount (`test_a_refund_over_the_late_cleared_amount_is_refused_and_writes_nothing`); no-write checks (`test_authorization_is_refused_without_funds_or_on_a_blocked_account`, `test_a_cleared_movement_cannot_be_cleared_again_or_reversed`, `test_a_partial_refund_or_a_refund_before_clearing_is_refused`); expiry evidence and elapsed time (`test_expiry_requires_evidence_and_elapsed_time_never_releases_the_hold`); the authorization boundary at the available amount (`test_authorization_takes_exactly_the_available_amount_and_one_cent_more_is_refused`).
- The `ACCOUNT_CLOSED` branch of `authorize_card` is covered by `test_authorization_on_a_closed_account_is_refused_and_writes_nothing`, but its direct-SQL setup stays open under the Open decision above, so it is not listed as closed.
- Not a test, recorded separately: the restriction UPDATE statements in `tests/integration/test_cards.py` are scoped to `WHERE account_id = 'acct-1'` (Minor closure, head `b733389`).

## Earlier Verified record (superseded)

- JDC decided on 2026-10-10 that TASK-16 is Verified on merged head `0ce8071` (PR #43), on the Tester pass in `docs/evidence/TASK-16-tester-report-2.md` (PR #44). Recorded in the Specs repository as DEC-0038.
- Superseded for the current head by the Status decision above. Kept as history; it is not the current status.

## Resolved items

- Resolved by merged Code PR #48 (merge `aeb3b2b`; the PR changed only `tests/integration/test_cards.py`): fingerprint replay and conflict for authorize, clear and refund (`test_a_replayed_authorization_returns_the_stored_outcome_and_a_changed_one_conflicts`, `test_a_replayed_clearing_returns_the_stored_outcome_and_a_changed_one_conflicts`, `test_a_replayed_refund_returns_the_stored_outcome_and_a_changed_one_conflicts`); response balances (`test_response_balances_match_the_database_for_authorize_clear_reverse_and_refund`); full counts in the reused-id test (`test_a_reused_movement_id_is_invalid_transition_and_declared`). No Tester pass covers this change yet (see Status decision). Owner: Builder (closed).
- Resolved by merged Code PRs #41 (merge `1458974`, which closed part of the TASK-16 Minors, including card test additions), #47 (merge `e20fafb`, refund, reuse, boundary and rejection Minors) and #48 (above). Specs DEC-0038 says "the Minors of Code PR #41 remain open and scheduled"; that Specs sentence is not changed here and is part of the JDC decision. Owner: Builder (closed).
- Minor closure (Stream B): the closed-account card refund test derives its expected balance from the setup amounts (funded, authorized and refunded cents) instead of the literal 1000. Test: `test_a_card_refund_is_accepted_on_a_closed_account` in `tests/integration/test_cards.py`; commit `8ed896b`. Owner: Builder (closed).

## Scheduled items

- Open Minor from the TASK-16 reviews: none. The authorization boundary is covered by `test_authorization_takes_exactly_the_available_amount_and_one_cent_more_is_refused` (`tests/integration/test_cards.py`, added in `b733389`). The remaining open decision is the Open decision above.
