# Work item: TASK-20 — outgoing risk restriction set/clear and enforcement

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.9.1` / `3a2e4b26070fc4d43bb52182991c72693c67fb7d`
- TASK and affected IDs: `TASK-20`; `FR-10`; `API-17`; `INV-11`; `DATA-01`, `DATA-06`; `TEST-10` (risk restriction blocks outgoing ACH, transfers and card authorization, and permits incoming credit, reads and correction). Governing trace: `specs/08-verification.md` section 9.1 (TASK-20 row) and `specs/09-delivery-plan.md` TASK-20.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.
- Dependencies: `TASK-17` merged and recorded Implemented (true on `main` at `00e45c6`).
- Decisions in force: DEC-0042 (JDC, 2026-10-10: a risk restriction is accepted on open and closed accounts, without a status check), specs/02 section 7 (controlled value `none|outgoing_blocked`; only `risk_controller`; no balance effect).

## Acceptance (paraphrased from the Specs)

- `risk_controller` alone sets or clears the outgoing block (API-17) with an opaque `decision_reference` and an idempotent `instruction_id`. The change has no balance effect (FR-10).
- Setting a block that is already set, or clearing one that is not set, is refused with `INVALID_TRANSITION` (409), stored. The requested state must differ (API-17 prerequisite).
- A set block rejects new outgoing ACH, internal transfers and card authorization with `OUTGOING_BLOCKED`. It permits incoming credit, required resolution of accepted movements, returns, reversals and approved corrections (TEST-10, INV-11, specs/02 section 7).
- Exact replay of the same key and fingerprint returns the stored HTTP 200 result with no second effect. A changed fingerprint is `IDEMPOTENCY_CONFLICT` with no effect.
- Each change appends one attributable trace row (DATA-06).
- A restriction is accepted on a closed account (DEC-0042).

## Scope

- Application command `set_risk_restriction` (API-17) and one storage operation that sets `accounts.restriction` and `accounts.restriction_decision_reference` together (the schema requires both or neither).
- Enforcement of the block already exists in outgoing ACH, internal transfers and card authorization. TASK-20 adds the end-to-end TEST-10 checks that prove the permitted side.
- No HTTP route. The FastAPI binding is TASK-25.
- No change to any approved requirement, schema or contract.

## Decisions taken where the Specs are silent (for JDC to redirect)

- The `risk_controller` response is HTTP 200 with `{account_id, restriction}`, per the contract (`RestrictionData`).
- `set` stores the decision reference on the account; `clear` removes it (`restriction_decision_reference` null). Decision references are not required to be unique, because the Specs define no uniqueness rule for restrictions. API-17 is keyed by `instruction_id`, and the Specs declare no reuse rule for it, so DEC-0026 does not apply.
- The restriction is accepted on a closed account (DEC-0042, approved by JDC).
- The trace row's `external_reference` carries the opaque `decision_reference`, as for corrections.

## Non-claims

- No risk decision logic. ABM never decides risk (specs/02 section 7, specs/06 section 4).
- No HTTP route, envelope or status mapping is verified here (TASK-25).

## Implementation and evidence

- Code PR #65, merged to `main` as `02d122f`. JDC approved the exact head `32450b8` in the session, 2026-10-10.
- The merged tree differs from `32450b8` only by the Specs pointer PR #66 (`5b120bf`, v1.9.1) that landed on `main` before this merge. The feature code is identical to the tested head.
- Tester record: [`docs/evidence/TASK-20-tester-report.md`](../evidence/TASK-20-tester-report.md). Code PASS on `32450b8`; docs review FAIL on `2b00cc3`, corrected in `9db0ed8`.
- Tests: `tests/integration/test_risk_restriction.py` (8 tests). Full suite 743 passing on the tested head.

## Scheduled items

- Closed-account restriction test pinning DEC-0042 (set and clear on a closed account). Owner Builder. Trigger: TASK-21 (closure).
- Resolved by TASK-23 PR #79: outgoing ACH settle and return remain permitted while the block is set.
- Resolved by TASK-23 PR #79: the clear-path trace asserts its operation and decision reference.

## Process record

- Independent review evidence was not stated in the Code PR description before merge, and the evidence file was committed after the merge. This does not meet the merge rule in `docs/governance/repository-policy.md` ("Approval and merge authority"). Found in the TASK-22 review on 2026-10-10. Recorded here so the Verified decision is made with it in view.

## Remediation (Tester FAIL on `efd6c55`)

- Open Major (M-1): permitted resolution of accepted card movements under the block was untested. The acceptance (clearing of an authorized card movement and late clearing, DEC-0031, while the block is set) had no test.
- Fix: `test_block_permits_clearing_of_authorized_card_movements_and_late_clearing` in `tests/integration/test_risk_restriction.py`. It authorizes one card movement and reverses another before the block, sets the block, then clears the authorized movement (`cleared`) and late-clears the reversed one (`late_cleared`). It asserts both are permitted, the balance is 400, and the block is still set.
- Mutation: blocking `clear_card` with `OUTGOING_BLOCKED` makes the test fail; the source was then reverted to its committed form.
- Checks on the fix head: `tests/integration/test_risk_restriction.py` 9 passed; `ruff`, `mypy` pass. Full-suite run and fresh Tester pass on the fix head are pending.
