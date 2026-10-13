# Work item: TASK-22 — seven-year retention evaluation and non-public legal-hold port

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.9.3` / `e72391c0f53d678c6e013cc0f1d9808f730994fa`
- TASK and affected IDs: `TASK-22`; `FR-16`; `INV-12`; `DATA-07`; `DEC-0008`, `DEC-0010`, `DEC-0012`; `BT-08`; `TEST-19` (retention row starts with null timestamps; closure and later final resolution set and advance both; seven-year predicate; legal hold always blocks eligibility), `TEST-37` (legal-hold and retention evaluation are not public HTTP and cannot delete anything), `TEST-45` (legal-hold set and clear accept only `retention_controller` through the non-public port, with record target checks, fingerprint conflict without mutation, exact replay, atomic commit). Governing trace: `specs/08-verification.md` section 9.1 (TASK-22 row) and `specs/09-delivery-plan.md` TASK-22.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.
- Dependencies: `TASK-21` merged and recorded Implemented (true on `main` at `6653ce1`).
- Decisions in force: DEC-0008 (evaluate retention and legal hold; no deletion; no automatic deletion), DEC-0010 (`retention_controller` owns legal-hold decisions through a non-public port), DEC-0012 (one account-level hold covering all dependent records; timestamps null until closure or latest resolution), DEC-0046 (the retention row stores its dates; closure sets them; each permitted late event advances both in its own transaction; seven calendar years; February 29 maps to February 28 in a non-leap year).

## Acceptance (paraphrased from the Specs)

- Each account has one retention row with `final_at` and `eligible_after` null until closure (TEST-19, DEC-0012).
- Closure sets both. Each permitted late event after closure (return, refund, late clearing, correction) advances both in its own transaction (DEC-0046). `eligible_after` is seven calendar years after `final_at`.
- The seven-year predicate keeps in-policy accounts and every dependent record. An account legal hold always blocks eligibility (TEST-19).
- `retention_controller` alone sets or clears the account-level legal hold through a non-public port. The instruction carries `instruction_id`, `account_id`, `record_type` equal to `account`, `record_id` equal to `account_id`, `action` (`set` or `clear`), and an opaque `decision_reference` (TEST-45, specs/03 section 8).
- The legal-hold change is atomic with its trace row and its idempotency outcome. Replay is exact, and a fingerprint conflict writes nothing (TEST-45).
- No public HTTP route exposes retention or legal-hold evaluation, and no operation deletes an account or a dependent record (TEST-37).

## Scope

- Retention advance on each permitted late event after closure: returns, refunds, late clearing, and corrections. Each advance is in the same transaction as the event.
- A read-only retention evaluation (`final_at`, `eligible_after`, legal hold, and whether the account is eligible at a given instant).
- The non-public `retention_controller` legal-hold command and its storage operation.
- No HTTP route. The FastAPI binding is TASK-25. No deletion.

## Decisions taken where the Specs are silent (for JDC to redirect)

- A late event advances the stored dates only when the account is closed. Retention starts at closure or the final resolution of a permitted later event, whichever is later (specs/02 section 9). Before closure, both dates stay null.
- A legal-hold set on an already held account, or a clear on an account that has no hold, is refused with `INVALID_TRANSITION` (409), stored, with no write. The requested state must differ, as for the risk restriction. Approved by JDC as DEC-0047 (Specs v1.9.4). `ACCOUNT_NOT_FOUND` is stored; a `record_type` or `record_id` mismatch is `VALIDATION_ERROR` and is not stored. Set and clear both trace.
- A legal-hold instruction on an unknown account is `ACCOUNT_NOT_FOUND` (404), stored. A wrong `record_type` or `record_id` is `VALIDATION_ERROR` (400), not stored.
- The response data is `{account_id, legal_hold}`. The port is not public, so no envelope is defined here.
- Legal hold may be set before or after closure (DEC-0012, specs/02 section 9).

## Non-claims

- No deletion and no automatic deletion (DEC-0008).
- No eligibility action, purge, or archive. Evaluation is observable only.
- No HTTP route or envelope (TASK-25).

## Implementation and evidence

- Code PR #74, merged to `main` as `9811a61` (head `caacace`; JDC approved the exact head in the session, 2026-10-10). Tester record: [`docs/evidence/TASK-22-tester-report.md`](../evidence/TASK-22-tester-report.md). Pass 1 on `07d12eb` found two Majors, both fixed; pass 2 on `caacace` PASS. Full suite 770 passing. The legal-hold refusal rule is DEC-0047 (Specs v1.9.4).

## Scheduled items

- Resolved by TASK-23 PR #79: the late-event docstring names the cases in that module and points to `test_retention.py` for incoming return.
- Resolved by commit `2cc5ae0` (chore: point the Code repository at Specs v1.9.16, DEC-0075): `README.md` now states `v1.9.16`; the Minor is closed.

## Process record

- Independent review evidence was not stated in the Code PR description before merge, and the evidence file was committed after the merge. This does not meet the merge rule in `docs/governance/repository-policy.md` ("Approval and merge authority"). Found in the TASK-22 review on 2026-10-10. Recorded here so the Verified decision is made with it in view.
- TASK-22 pass 1 (`07d12eb`) is recorded in `docs/evidence/TASK-22-tester-report-1.md`. Its DEC-0047 check was not made against the Specs text by the reviewer; the pass-2 record states this.

## Verified record

- Tester PASS on the merged head `caacace`, merged as `9811a61` (PR #74): `docs/evidence/TASK-22-tester-report.md`. Pass 1 (`07d12eb`) found two Majors, resolved before the final pass; see Process record for the review-timing gap.
- All Scheduled items above are resolved; none remains open in this file.
