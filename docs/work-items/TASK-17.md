# Work item: TASK-17 — cross-flow idempotency conformance, exact stored-data replay, and conflict tests for every command

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.8.3` / `c24abb2b31f0969c8e8c6eee24d9187a52df6c0b`
- TASK and affected IDs: `TASK-17`; `TEST-15`, `TEST-46`; `specs/02` idempotency rules and `specs/04` section 3 (every command)
- Decision records: `DEC-0011` (which outcomes are stored), `DEC-0014`, `DEC-0023`, `DEC-0025`, `DEC-0026` (reuse is `INVALID_TRANSITION`)
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required
- Dependencies: `TASK-10` through `TASK-16` merged (true on `main` at `d7b31fa`)

## Acceptance (paraphrased from the Specs; TEST-15 and TEST-46 are the sources)

- The same idempotency key and fingerprint exactly replays the stored 2xx, deterministic 404, non-conflict 409, and 422 status and body, with only replay metadata changed (TEST-15).
- A changed fingerprint returns `IDEMPOTENCY_CONFLICT` and stores nothing.
- 400, 401, 403, 500 and 503 are never stored; a later request with the same key is evaluated fresh (TEST-15, DEC-0011).
- Every command is covered, not only the card and transfer commands (TEST-46).

## Implementation

- Code PR #53, merged to `main` as `00e45c6` (head `5bf80f8a84d9c05426d908eeb8dcfd343392c790`, identical tree `ff73429e2f0386e1186c75a13a955cdfa7f02443`).
- Added `tests/integration/test_idempotency_conformance.py`: 98 tests over a 16-scenario table covering every command group above. No source change.

## Evidence

- Tester record: [`docs/evidence/TASK-17-tester-report.md`](../evidence/TASK-17-tester-report.md). Gates green (709 tests passed); mutants of the replay branch and a fingerprint input are caught.

## Scheduled items

- 401 non-stored status has no test (edge-level). Owner Builder. Trigger: a follow-up on the edge work.
- ACCOUNT_CLOSED cases in the conformance table wait for TASK-21 (closure).
- Closed-account card cases that set closure by direct SQL stay with TASK-21.

## Non-claims

- No production readiness claim.
- The `specs/09` row for TASK-17 still reads Draft. Its status change is normative and needs JDC approval; it is not made here.
