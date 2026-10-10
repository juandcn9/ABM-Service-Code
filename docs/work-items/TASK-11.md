# Work item: TASK-11 — account projection, history reads, and reconciliation trace

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-11`; `FR-11`, `FR-12`, `FR-13`; `API-02`, `API-03`, `API-19`; `BT-04`, `BT-05`; `INV-05`
- Decision, gap, or risk records: none new; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: scoped account reads (lifecycle, posted, held, available, restriction, active holds), retained account history in stable sequence order with bounded cursor pagination, and the reconciliation trace through one captured inclusive cutoff.
- Included files/components: `src/abm/application/reads.py` (`get_account`, `get_history`, `get_trace`); `src/abm/ports/storage.py` (read ports and `TraceRow`); `src/abm/persistence/sqlite_store.py` (read queries); `tests/integration/test_reads.py`.
- Explicit exclusions: the FastAPI routes and response envelopes (`TASK-25`); reconciliation pagination model tests (`TASK-24`); any write (no read stores an outcome).
- Dependencies and entry gate: `TASK-07` and `TASK-10`, both merged to `main`.

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_reads.py`, real SQLite files): a new account reads as zero state; posted, held and derived available balances are consistent; released holds are not listed or counted; available may be negative only when the ledger allows it; a reader sees only its exact account, and an unknown account is not found; denied reads never touch storage.
- History: stable sequence order; pages without gaps or duplicates; the exact page boundary has no phantom next page; query bounds enforced; an unknown account is not found and another scope is denied.
- Trace: the first page captures the cutoff and later pages honour it; a full walk returns every record once in order; records expose immutable matching fields; an empty database has cutoff zero; a cutoff beyond the committed end is refused; only the reconciliation reader may read the trace; query bounds enforced.
- Reads change nothing and store no outcome (asserted by table counts).
- Required broader gates: local pytest, ruff, format, mypy, both validators; `validate-governance` and `quality-gates` on the PR head.
- Failure and concurrency: a read runs inside one consistent snapshot (BT-04, BT-05). Cross-process concurrency is not tested here (`TASK-24`, `TASK-28`).

## Implementation notes

- Reads run in one read transaction; the cursor is the stored `sequence`, so pages are stable under concurrent appends.
- Trace cutoff is captured on the first page and carried in the cursor; later pages cannot see records appended after it.
- Available balance is derived (posted minus active holds), not stored, so it cannot drift from the holds.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: locally `pytest` 497 passed on this branch after merging `main`; `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, `validate_governance.py`, `validate_toolchain.py` pass; CI results are on the PR.
- Review findings/resolution: pending (fresh-context review and Tester verification of the final head).
- Residual risks: none new beyond the cross-process concurrency limit above.
- Next safe action: TASK-13 (incoming ACH) after this PR merges, or the next dependency-ready TASK in `specs/09-delivery-plan.md`.

## Review fixes (PR #16)

- Major 1: an oversized cursor (2**63 or more) raised an unhandled `OverflowError` at the SQLite binding. Cursors and the trace cutoff are now capped at the SQLite INTEGER maximum and return `VALIDATION_ERROR`. Covered by `test_oversized_or_negative_cursors_are_validation_errors`.
- Minor: a no-op statement left in a test was removed; the paging comment moved above its line.
- Carried to later tasks (not TASK-11 defects):
  - `TASK-25`/`TASK-27`: `specs/04-api.md` (API-02, API-03) and the OpenAPI API-19 text require safe access evidence for authorized reads. Reads emit none today; the owning task must add it.
  - `TASK-13` onward (write paths): `contracts/openapi.yaml` TraceRecord requires an evidence or external reference for settlement, return, clearing and refund effects. The schema has no CHECK for this, so each write path must guarantee it.
