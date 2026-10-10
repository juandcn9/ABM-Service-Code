# Work item: TASK-19 — append-only approved corrections and permitted negative behavior

**Status:** Draft (opened; implementation on `feat/task-19-corrections`)

## Authority

- Specs version and exact SHA: `v1.9.0` / `5fcb90503ab38bbc1eb29fdcf7505767d842acb2`
- TASK and affected IDs: `TASK-19`; `FR-09`; `API-16`; `INV-04`, `INV-08`, `INV-10`, `INV-16`; `DATA-02`, `DATA-04`, `DATA-08`; `TEST-09` (approved correction appends a linked entry; no existing record changes), `TEST-10` (correction permitted under a risk restriction). Governing trace: `specs/08-verification.md` section 9.1 (TASK-19 row) and `specs/09-delivery-plan.md` TASK-19.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.
- Dependencies: `TASK-17` merged and recorded Implemented (true on `main` at `00e45c6`).
- Decisions in force: DEC-0026 (a caller-supplied `correction_id` reuse is `INVALID_TRANSITION`), DEC-0028 (the correction `decision_reference` is stored in `movements.decision_reference` through migration `0003`).

## Acceptance (paraphrased from the Specs)

- An externally approved correction (API-16, `correction_authority` only) appends exactly one ledger entry of effect kind `correction` with the stated direction and amount, linked to its decision reference (FR-09, TEST-09).
- No existing ledger entry, movement, or trace row changes. History is never rewritten (INV-04, INV-08).
- A correction may create a negative current balance (INV-10). A correction is permitted while a risk restriction is set (TEST-10, specs/02 section 7).
- A correction is accepted on a closed account (INV-16). Closure itself is TASK-21, so this task does not test closed accounts.
- Exact replay of the same key and fingerprint returns the stored 201 with no second effect; a changed fingerprint is `IDEMPOTENCY_CONFLICT` with no effect.

## Scope

- Application command `create_correction` (API-16) and the storage operations it needs: store `decision_reference` on the correction movement and `correction_of_entry_id` on the correction entry (both columns already exist through migration `0003`).
- No HTTP route. The FastAPI binding is TASK-25.
- No change to any approved requirement, schema, or contract.

## Decisions taken where the Specs are silent (for JDC to redirect)

- `correction_id` is the correction movement's `movement_id` (specs/05 field map). A reused `correction_id` returns `INVALID_TRANSITION` (409), stored, per DEC-0026.
- One correction per decision (specs/03 correction-decision driver: "one append-only correction per decision"). A `decision_reference` already used by a correction returns `INVALID_TRANSITION` (409), stored. The check runs inside the serialized write transaction. No database UNIQUE index is added, because the schema contract does not specify one.
- `corrected_entry_reference`, when present, must name an existing ledger entry of the same account. If it does not, the command returns `INVALID_TRANSITION` (409), stored. This is the only declared 409 code for API-16. The field stays optional in the request.
- Correction direction is `credit` or `debit` (contract enum). Any other value is `VALIDATION_ERROR` and not stored.
- The trace row's `external_reference` carries the opaque `decision_reference`, so reconciliation sees the decision. The ledger row's `external_reference` stays empty (DEC-0028 keeps the decision on the movement).

## Non-claims

- No approval logic. ABM never identifies approvers, stores case payloads, or evaluates evidence (specs/02 section 6).
- No partial or multiple corrections are modeled beyond the single append described above.
- Closed-account correction cases wait for TASK-21, which adds closure.

## Implementation and evidence

- Pending: Code PR on `feat/task-19-corrections`, Tester pass, and JDC approval of the exact head SHA before merge.

## Scheduled items

- None yet. Closed-account correction tests (INV-16) are owned by TASK-21 (closure).
