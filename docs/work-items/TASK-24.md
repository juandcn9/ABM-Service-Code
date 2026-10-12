# Work item: TASK-24 — deterministic reconciliation and read pagination; model-based lifecycle coverage

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.9.8` / `7b98166b32411c587cdda0ec9bc35bbf5b7741ff` (DEC-0053).
- TASK and affected IDs: `TASK-24`; `FR-11` to `FR-14`; `API-02`, `API-03`, `API-19`; `NFR-06`; `TEST-12`, `TEST-13`, `TEST-47`. Shared identifiers `TEST-39` and `TEST-41` are layered to `TASK-26` by DEC-0053 and are not claimed here.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.
- Dependencies: `TASK-11` and `TASK-21` recorded Implemented (true on `main`).

## Scope

- Pagination of account history (`API-03`) and of the reconciliation trace (`API-19`): deterministic order, no gaps, no duplicates, and the trace cutoff honored across pages (`TEST-12`, `TEST-47`, `NFR-06`).
- Model-based lifecycle coverage: seeded random command sequences checked against invariants after every step (balances equal the ledger, history walks return every row once in order, the trace is complete through its cutoff, readiness stays clean).
- Closure eligibility and permitted late evidence (`TEST-13`) are covered by the TASK-21 suite and are not repeated here.

## Implementation and evidence

- Code PR #83, merged as `6a6b9f2` at approved head `e3c616f`: between-pages pagination (`TEST-47`) and the seeded lifecycle model (`TEST-12`, `NFR-06`). Review: fresh-context Tester PASS on `e3c616f`, recorded in the PR before merge.
- Code PR #86, merged as `668f1b4` at approved head `025037b` (JDC approved the exact head in the session, 2026-10-10): outgoing ACH (create, submit, settle, reject, cancel, return) added to the model. Review: fresh-context Tester PASS on `025037b`, recorded in the PR before merge. Mutants on the settle and return paths caught.
- The lifecycle model runs 400 steps over five fixed seeds, checks every invariant after every step, and requires each command family to be accepted at least once per seed (rejection across the seeds together).
- Gates on `025037b`: ruff check and format clean; mypy clean (74 files); governance passed; full pytest 797 passed.
- Evidence record: `docs/evidence/TASK-24-tester-report.md` (covers PR #83; PR #86 is recorded in the PR description and in this work item).

## Non-claims

- `TEST-39` (safe escalation signal for aged pending items) and `TEST-41` (attributable safe read evidence) are finalized by `TASK-26` under DEC-0053. No public interface is added here, and no schema change.
- No HTTP route, envelope, or status mapping for the read operations (`TASK-25`).

## Scheduled items

- Minor (PR 86): the cross-seed test name is narrower than what it checks. Owner Builder. Trigger: next TASK-24 change.
- Minor (PR 86): a broken ledger write in settle or return fails with a generic error, not a clear invariant message. Owner Builder. Trigger: a later hardening task.
- Runtime: the lifecycle file takes about 70 to 85 seconds. Owner Builder. Trigger: when the suite becomes a CI bottleneck.

- Outgoing ACH in the model sequence: Owner Builder. Trigger: this task, before Implemented.
- `TEST-39` and `TEST-41` facets: Owner Builder. Trigger: `TASK-26` (DEC-0053).
- HTTP read responses and error envelopes: Owner Builder. Trigger: `TASK-25`.

## Verified record

- Tester PASS on `e3c616f` (PR #83, merged `6a6b9f2`) and a second PASS on `025037b` (PR #86, merged `668f1b4`), which adds outgoing ACH to the model: `docs/evidence/TASK-24-tester-report.md`. The Major found on `24a0f55` was fixed in `603314a` and covered by the later pass.
- Scheduled items above stay open as listed.
