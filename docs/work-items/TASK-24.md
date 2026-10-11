# Work item: TASK-24 — deterministic reconciliation and read pagination; model-based lifecycle coverage

**Status:** Draft

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

- Code PR #83, merged to `main` as `6a6b9f2` at approved head `e3c616f` (JDC approved the exact head in the session, 2026-10-10). The merged tree differs from `e3c616f` only by the Specs pointer PR #84 (v1.9.8) that landed on `main` before the merge.
- Tests: `tests/integration/test_pagination_between_pages.py` (2 tests, `TEST-47`); `tests/integration/test_lifecycle_model.py` (3 seeded runs, 80 steps each, `TEST-12`, `NFR-06`).
- Independent review: fresh-context Tester PASS on `e3c616f`, recorded in the PR #83 description before merge. Earlier passes found a Major (the history test did not compare the full history) and a Minor (the activity check counted rows, not commands); both are fixed. Mutants caught: skipped history row, ignored trace cutoff, and no accepted commands.
- Gates on `e3c616f`: ruff check and format clean; mypy clean (74 files); governance passed; full pytest 794 passed.

## Remaining work before TASK-24 can be Implemented

- Add outgoing ACH (create, submit, settle, reject, cancel, return) to the random command sequence of `tests/integration/test_lifecycle_model.py`, so that the model covers every lifecycle the Specs define for reads. This needs a new reviewed head.
- Re-run the gates and an independent review on that head, then request JDC approval of the exact head.

## Non-claims

- `TEST-39` (safe escalation signal for aged pending items) and `TEST-41` (attributable safe read evidence) are finalized by `TASK-26` under DEC-0053. No public interface is added here, and no schema change.
- No HTTP route, envelope, or status mapping for the read operations (`TASK-25`).

## Scheduled items

- Outgoing ACH in the model sequence: Owner Builder. Trigger: this task, before Implemented.
- `TEST-39` and `TEST-41` facets: Owner Builder. Trigger: `TASK-26` (DEC-0053).
- HTTP read responses and error envelopes: Owner Builder. Trigger: `TASK-25`.
