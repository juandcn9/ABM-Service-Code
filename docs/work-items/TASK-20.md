# Work item: TASK-20 — outgoing risk restriction set/clear and enforcement

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.0` / `5fcb90503ab38bbc1eb29fdcf7505767d842acb2`
- TASK and affected IDs: `TASK-20`; `FR-10`; `API-17`; `INV-11`; `DATA-01`, `DATA-06`; `TEST-10` (risk restriction blocks outgoing ACH, transfers and card authorization, and permits incoming credit, reads and correction). Governing trace: `specs/08-verification.md` section 9.1 (TASK-20 row) and `specs/09-delivery-plan.md` TASK-20.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.
- Dependencies: `TASK-17` merged and recorded Implemented (true on `main` at `00e45c6`).
- Decisions in force: DEC-0026 (create operations keyed by a caller-supplied identifier refuse reuse with `INVALID_TRANSITION`), specs/02 section 7 (controlled value `none|outgoing_blocked`; only `risk_controller`; no balance effect).

## Acceptance (paraphrased from the Specs)

- `risk_controller` alone sets or clears the outgoing block (API-17) with an opaque `decision_reference` and an idempotent `instruction_id`. The change has no balance effect (FR-10).
- Setting a block that is already set, or clearing one that is not set, is refused with `INVALID_TRANSITION` (409), stored. The requested state must differ (API-17 prerequisite).
- A set block rejects new outgoing ACH, internal transfers and card authorization with `OUTGOING_BLOCKED`. It permits incoming credit, required resolution of accepted movements, returns, reversals and approved corrections (TEST-10, INV-11, specs/02 section 7).
- Exact replay of the same key and fingerprint returns the stored HTTP 200 result with no second effect. A changed fingerprint is `IDEMPOTENCY_CONFLICT` with no effect.
- Each change appends one attributable trace row (DATA-06).

## Scope

- Application command `set_risk_restriction` (API-17) and one storage operation that sets `accounts.restriction` and `accounts.restriction_decision_reference` together (the schema requires both or neither).
- Enforcement of the block already exists in outgoing ACH, internal transfers and card authorization. TASK-20 adds the end-to-end TEST-10 checks that prove the permitted side.
- No HTTP route. The FastAPI binding is TASK-25.
- No change to any approved requirement, schema or contract.

## Decisions taken where the Specs are silent (for JDC to redirect)

- The `risk_controller` response is HTTP 200 with `{account_id, restriction}`, per the contract (`RestrictionData`).
- `set` stores the decision reference on the account; `clear` removes it (`restriction_decision_reference` null). Decision references are not required to be unique, because the Specs define no uniqueness rule for restrictions.
- The restriction is not refused on a closed account. The Specs do not list it among the closed-account permissions (INV-16), and closure is TASK-21. This is the most likely point for JDC to redirect.
- The trace row's `external_reference` carries the opaque `decision_reference`, as for corrections.

## Non-claims

- No risk decision logic. ABM never decides risk (specs/02 section 7, specs/06 section 4).
- Closed-account restriction cases wait for TASK-21.

## Implementation and evidence

- Pending: docs PR (this record), Code PR on `feat/task-20-risk-restriction`, Tester pass, and JDC approval of the exact code head before merge.

## Scheduled items

- None yet.
