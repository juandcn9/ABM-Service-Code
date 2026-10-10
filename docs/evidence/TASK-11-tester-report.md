# TASK-11 independent Tester report (sanitized record)

Provenance: fresh-context Tester run on 2026-10-10, read-only with respect to the Code repository (no edits, no commits, no config changes, no pushes, no refs). The Tester did not build TASK-11. Work was done in a detached worktree at the revision below, which was removed afterwards without force.

## Revision verified

- Merge commit: `f201f51b8e8573c97a2d5cf36b7095b95319e4c5` (HEAD of the detached worktree, confirmed)
- PR: #16 (`task-11-reads`), merged on `main`
- Work item: `docs/work-items/TASK-11.md` at that commit (Specs `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`)

## Environment

- Windows 11 Home 10.0.26300, Git Bash
- Repository venv interpreter from the main checkout (`.venv\Scripts\python.exe`), run from the worktree; `pyproject.toml` sets `pythonpath = ["src", "."]`, so tests import the worktree `src`
- pytest run with `-p no:cacheprovider`; the venv does not install `abm`, so imports resolve to the worktree

## Result

PASS with findings. Blocker 0, Major 0, Minor 4.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| HEAD confirmed | PASS | `git rev-parse HEAD` = `f201f51b8e8573c97a2d5cf36b7095b95319e4c5`, subject "Merge pull request #16 from juandcn9/task-11-reads" |
| mypy src harness tests scripts | PASS (exit 0) | "Success: no issues found in 45 source files" |
| pytest -q | PASS (exit 0) | 501 passed in 147.02s |
| ruff check . | PASS (exit 0) | "All checks passed!" |
| ruff format --check . | PASS (exit 0) | "71 files already formatted" |
| scripts/validate_governance.py | PASS (exit 0) | required files 11; Specs pointer v1.0.1 / 5d1cd410...; governance headings, workflow pin, placeholders and secret patterns passed |
| Acceptance: account reads | Covered by tests | `test_new_account_reads_as_zero_state`, `test_balances_are_posted_held_and_derived_available`, `test_released_holds_are_not_listed_or_counted`, `test_available_balance_may_be_negative_when_the_ledger_allows_it`, `test_reader_is_limited_to_its_exact_account_and_unknown_is_not_found`, `test_denied_reads_never_touch_storage` |
| Acceptance: history paging | Covered by tests | Stable sequence order, gap-free walk, exact page boundary without phantom next page, query bounds, unknown account and other-scope denial |
| Acceptance: trace | Covered by tests | Cutoff captured on first page and honoured later, full walk once in order, immutable matching fields, empty DB cutoff 0, cutoff beyond committed end refused, reconciliation-only access, query bounds |
| Acceptance: no writes | Covered by tests | `test_reads_change_nothing_and_store_no_outcome` |
| Snapshot (BT-04, BT-05) | Code and test read | `read_transaction` issues `BEGIN` and all read queries run inside it; `test_a_read_transaction_keeps_one_snapshot_while_another_connection_commits` uses a second connection in one process |
| Cursor bounds | Code and test read | `_count` rejects bool, negative and above `MAX_CURSOR` (2**63-1) with `VALIDATION_ERROR`; limits bounded (history 1..200, trace 1..1000); oversized cursor test covers history and trace |
| Trace ordering and cutoff | Code read | `trace_page` uses `sequence > after AND sequence <= cutoff ORDER BY sequence ASC LIMIT n+1`; a requested cutoff above `MAX(sequence)` returns `VALIDATION_ERROR` |
| Account scope | Code read | `authorize` denies unless the role has the operation and `caller.account_scope == account_id`; denial is the same generic `FORBIDDEN_SCOPE` |
| Mutation testing | 7 of 7 caught | See the mutant table |

## Mutants

Self-contained copy of `src`, `tests`, `harness`, `migrations`, `pyproject.toml`; one mutation per run; `pytest -q -p no:cacheprovider tests/integration/test_reads.py` run from inside the copy (41 tests on the base). Each replacement was asserted to match exactly once.

| Mutant | Change | Result | Caught by |
|---|---|---|---|
| M1 no read snapshot | `read_transaction` does not issue `BEGIN` | CAUGHT (1 failed) | `test_a_read_transaction_keeps_one_snapshot_while_another_connection_commits` |
| M2 trace ignores carried cutoff | `cutoff = current` (drops the echoed cutoff) | CAUGHT (1 failed) | `test_trace_first_page_captures_the_cutoff_and_later_pages_honor_it` |
| M3 exclusive trace cutoff | `t.sequence <= ?` changed to `< ?` | CAUGHT (3 failed) | first-page test, full-walk test, immutable-fields test |
| M4 unbounded history cursor | `_count(after_sequence, 0)` without `MAX_CURSOR` | CAUGHT (2 failed) | `test_oversized_or_negative_cursors_are_validation_errors` (2**63 and 2**64 cases) |
| M5 scope check removed | `caller.account_scope != account_id` replaced by `False` | CAUGHT (3 failed) | scope-limit test, denied-reads test, other-scope history test |
| M6 released holds listed | removes `state = 'active'` filter in the holds query | CAUGHT (1 failed) | `test_released_holds_are_not_listed_or_counted` |
| M7 phantom next page | `len(rows) > size` changed to `>=` | CAUGHT (1 failed) | `test_history_exact_page_boundary_has_no_phantom_next_page` |

## Findings

Ranked. None is a Blocker or Major. All four Minor items are residual risks the work item already names, or notes for owning tasks. None is a TASK-11 defect.

1. Minor: the trace cutoff is client-echoed. If a caller omits `cutoff_sequence` on a later page, `get_trace` silently takes a fresh cutoff, and the walk can then include records committed after the first page. The read layer cannot prevent this; the API layer (TASK-25) must carry the cutoff in the cursor. Owner: TASK-25.
2. Minor: the snapshot test uses a second connection in one process. Cross-process isolation is not tested (work item: TASK-24/TASK-28).
3. Minor: immutability of trace fields is enforced by schema triggers, and no read test covers it (work item residual risk).
4. Minor: the "available only when the ledger allows" rule is tested for the negative result only (work item residual risk).

Process note (not a product finding): during this run the Tester ran `rm -rf` on a path that resolved to a shared session scratchpad `mutants/` directory, which other agents were writing to at the same time. It removed part of that directory (one entry was busy and not removed). The removed content was not the Tester's and cannot be restored by the Tester. The Tester then stopped deleting and moved its own mutant work to a separate directory. The other owner should be told to check their mutant directory.

## Not verified

- Cross-process concurrency and real multi-process SQLite locking (TASK-24/TASK-28).
- The HTTP layer, response envelopes, and safe access evidence for authorized reads (TASK-25/TASK-27).
- The CI run on the PR head (only the local gates were re-run here).
- Fresh-clone or Python 3.12.15 behaviour; the local interpreter version was not re-captured in this run.
- Whether the trace's client-side cutoff handling is correct in any API route (no routes in TASK-11).
- Full mutant coverage beyond the seven listed; the mutants target the read paths only.
