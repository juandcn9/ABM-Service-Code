# Work item: TASK-21 — closure eligibility, terminal state, and permitted late evidence

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.2` / `3866d63fc22079acc040be096a760d1660eec09a`
- TASK and affected IDs: `TASK-21`; `FR-14`; `API-18`; `INV-15`, `INV-16`, `INV-18`; `DATA-01`, `DATA-02`; `TEST-13` (closure fails with nonzero balance, active hold, or unresolved movement; eligible closure succeeds regardless of restriction, stays terminal, and admits only permitted late evidence). Governing trace: `specs/08-verification.md` section 9.1 (TASK-21 row) and `specs/09-delivery-plan.md` TASK-21.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.
- Dependencies: `TASK-13` through `TASK-20` merged and recorded Implemented (true on `main`; TASK-20 at `02d122f`).
- Decisions in force: DEC-0044 (an unresolved movement is one of `pending`, `accepted_with_hold`, `submitted`, `authorized_with_hold`), DEC-0042 (a risk restriction is accepted on a closed account), DEC-0030 (a card refund is permitted on a closed account), specs/02 section 2 (INV-15, INV-16) and section 8 (retention starts at closure).

## Acceptance (paraphrased from the Specs)

- `account_registrar` closes an account only when its current balance is zero, it has no active hold, and it has no unresolved movement (API-18, INV-15). Otherwise the closure is refused with `CLOSURE_PRECONDITION_FAILED` (422), stored, with no change.
- A successful closure is terminal: the account never reopens, and the restriction is unchanged (API-18, DEC-0042). One trace row is appended.
- A closed account refuses customer instructions with `ACCOUNT_CLOSED` (INV-16): new outgoing ACH, transfer, card authorization, and incoming notice or settlement.
- A closed account accepts only permitted late evidence (INV-16): a permitted late clearing of a reversed or expired card movement, a card refund, an incoming or outgoing return, and an approved correction. None of them reopens the account.
- Readiness reports `INTEGRITY_FAILED` if a ledger effect outside that permitted set is posted after closure (TASK-21 plan row, INV-18).

## Scope

- Application command `close_account` (API-18) and the storage operations it needs: read the open obligations (active holds and unresolved movements), and set the account to closed with its closure time.
- A readiness query for ledger effects posted after closure that are not permitted.
- Closed-account tests that use the real closure command instead of direct SQL. The existing direct-SQL refusal tests stay as they are.
- No HTTP route. The FastAPI binding is TASK-25.
- No change to any approved requirement, schema, or contract.

## Decisions taken where the Specs are silent (for JDC to redirect)

- Closing an account that is already closed returns `INVALID_TRANSITION` (409), stored. The Specs declare that code for API-18, and a closed account never reopens or closes again.
- The success response is HTTP 200 with `{account_id, status: "closed"}` (`ClosureData`, `ClosureSuccess`).
- Closure does not set the retention row's `final_at` or `eligible_after`. The schema requires both or neither, and deriving them from closure and late events is TASK-22 (retention).
- The post-closure readiness check compares timestamps. An effect in the same second as closure is not flagged (shortcut: same-second ledger effects are not ordered; upgrade by storing a ledger sequence at closure).

## Non-claims

- No retention evaluation or legal hold (TASK-22).
- No HTTP route, envelope, or status mapping (TASK-25).

## Implementation and evidence

- Pending: Code PR on `feat/task-21-closure`, Tester pass, and JDC approval of the exact code head before merge.

## Scheduled items

- None yet. Retention dates after closure belong to TASK-22.
