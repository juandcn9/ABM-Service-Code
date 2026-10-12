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

- JDC approved Code PR #53 at its exact head `5bf80f8a84d9c05426d908eeb8dcfd343392c790` (2026-10-10). Code PR #53, merged to `main` as `00e45c6` (head `5bf80f8a84d9c05426d908eeb8dcfd343392c790`, identical tree `ff73429e2f0386e1186c75a13a955cdfa7f02443`).
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

## Process record

- Independent review evidence was not stated in the Code PR description before merge, and the evidence file was committed after the merge. This does not meet the merge rule in `docs/governance/repository-policy.md` ("Approval and merge authority"). Found in the TASK-22 review on 2026-10-10. Recorded here so the Verified decision is made with it in view.

## Remediation (Tester FAIL on `00e45c6`)

- Open Major: no test that a 401 is not stored and that the same key is evaluated fresh (TEST-15, TEST-46; the work item gap table and plan step 2 name 401).
- Fix: `test_401_is_not_stored_and_the_same_key_is_evaluated_fresh` in `tests/integration/test_http_slice1.py`, beside the existing 401 test. It posts without caller context, asserts no `idempotency_outcomes` row for the key, then posts with valid context and asserts a fresh 201 with one `success` outcome. It lives in the HTTP slice rather than the application conformance file because the 401 is a transport-layer denial.
- Checks on the fix head: `tests/integration/test_http_slice1.py` 9 passed; `ruff check .` and `mypy src harness tests scripts` pass. Full-suite run and fresh Tester pass on the fix head are pending.
