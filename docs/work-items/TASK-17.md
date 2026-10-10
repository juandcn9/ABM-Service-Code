# Work item: TASK-17 — cross-flow idempotency conformance, exact stored-data replay, and conflict tests for every command

**Status:** Draft

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

## Coverage inventory (measured on `d7b31fa`)

| Command group | Existing replay or conflict tests | Gap |
|---|---|---|
| Registration (`register_account`) | 7 references | Confirm 404 and 422 replays are exact |
| Incoming ACH (notice, settle, return) | 2 | Replay of settle and return with the stored body; 404 and 422 replays |
| Outgoing ACH (create, submit, settle, reject, cancel, return) | 1 | Replay and conflict for each of the six operations |
| Internal transfer | 2 | 404 and 422 replays |
| Card (authorize, clear, reverse, expire, refund) | 10 | Reverse and expire replay and conflict |
| Reads | 1 (reads store nothing) | Confirm reads are never stored |
| Non-stored statuses (400, 401, 403, 500, 503) | none | Test that each is not stored and a retry is evaluated fresh |

## Plan

1. Build one conformance table: for each command, a successful call, a replay (same key and fingerprint), a conflict (same key, one field changed), a deterministic 404 and a 422, each checked for exact replay of status and body.
2. Add the non-stored status checks as their own tests, one per status.
3. Each new test must fail when its replay or conflict logic is removed (mutant check).
4. Code PR with the Builder Auditor's gates, `ponytail-review`, fresh-context review, then a Tester pass of the exact head. JDC approves the exact head.

## Non-claims

- No behavior change is expected. If a test shows a mismatch with the Specs, the Builder records a GAP and stops for JDC; the conformance test is not weakened to pass.
- Closed-account card cases that set closure by direct SQL stay with TASK-21.
