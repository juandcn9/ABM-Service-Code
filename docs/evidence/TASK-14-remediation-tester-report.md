# TASK-14 Tester report: origin/fix/task-14-minors @ 39af8c1

## Revision and chain
- origin/fix/task-14-minors: 39af8c170960 (39af8c1709605c97502b293610ef5c607a1169bd), commit "test: TASK-14 Tester N1 (two balance-only refusal checks compare full state)"
- Parent: d08f7bda (d08f7bda6730d54c53033ffd7a6c0f9ce694d630). Grandparent: 2dbca04 = origin/main at fetch time (2dbca0476f86dc990aa6b67fd0ef720a5fa6c50b).
- Fetch: `git fetch origin +refs/heads/fix/task-14-minors:... +refs/heads/main:...` exit 0. Two non-fatal "failed to delete .git/worktrees/... Permission denied" lines were printed during ref pruning (see Observations).

## Diff check
- `git diff --stat d08f7bd 39af8c1`: `tests/integration/test_outgoing_ach.py | 4 ++--`, 1 file, 2 insertions, 2 deletions. Only that file changed.
- Diff content: at the closing-transition test (`test_a_closing_transition_without_an_active_hold_moves_no_money`), `before = balances(conn)` became `before = state(conn)`, and `assert balances(conn) == before` became `assert state(conn) == before`. Nothing else changed.

## Worktree and venv
- Detached worktree `C:\Users\Admin\AppData\Local\Temp\abm-tester-14c` from 39af8c1. HEAD asserted 39af8c1 before and after; status clean at start.
- Venv `C:\Users\Admin\AppData\Local\Temp\abm-tester-14c-venv` (Python 3.12.10), outside the worktree. `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock` exit 0. `pip check` exit 0 ("No broken requirements found").

## Commands and results (all run in the worktree, venv Python/tools)
| Command | Exit | Result |
|---|---|---|
| `pytest -p no:cacheprovider -q tests/integration/test_outgoing_ach.py` | 0 | 24 passed |
| `pytest -p no:cacheprovider -q` (full suite, single process) | 0 | 1234 passed, 1 warning (StarletteDeprecationWarning, httpx/testclient; not related to this change), 453.87s |
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 182 files already formatted |
| `mypy src harness tests scripts` | 0 | Success: no issues found in 99 source files |
| `python scripts/validate_governance.py` | 0 | TASK-01 VALIDATION PASSED (11 required files; Specs pointer v1.9.14 / 0cca28b2) |

## N1 non-vacuity (worktree only; `src` mutation and test edits reverted)
Backups with SHA-256 saved to `C:\Users\Admin\AppData\Local\Temp\abm-tester-14c-backup\`:
- test file original SHA-256 F4880BDB5819338851C72AA6B9A114BA8C54778E0B37E01C6621B19647796F65
- outgoing_ach.py original SHA-256 5C0A95C8C1EE59C13E08DDC191A9013E6700CB4B6A0DAFBBFB2B7F78203BD6C1

Note: a first weakening attempt used a global string replace and changed five other `state` checks. It was discarded by restoring the backup (SHA verified) before the valid runs below.

- Scenario A: test weakened to balance-only (the two named checks only), no src change. Closing-transition test: 1 passed, exit 0.
- Scenario B: balance-only test plus a deliberate non-balance write in the closing-transition refusal branch of `src/abm/application/outgoing_ach.py` (`tx.add_evidence("n1-mutant-"+evidence, ...)` before the INVALID_TRANSITION return for no active hold). Result: 1 passed, exit 0. So balance-only comparison does NOT catch a non-balance write (confirms the gap N1 described).
- Scenario C: original full-state test (restored from backup, SHA verified) plus the same mutation. Result: FAILED `test_a_closing_transition_without_an_active_hold_moves_no_money` at line 520, `state(conn) == before`, diff at index 1: counts `(2, 3, 1, 5, 1)` vs `(2, 2, 1, 5, 1)` (movement_evidence 2 to 3). Exit 1. So the full-state check catches the write.
- Restore: `outgoing_ach.py` restored from backup, SHA verified matches original. `git status --short` empty, HEAD 39af8c1 confirmed.

## Findings
- Blocker: 0
- Major: 0
- Minor: 0 (the N1 Minor from d08f7bd is resolved: both named checks now compare the full state, and Scenario C shows the full state catches a non-balance write)
- Observation 1: `git fetch` printed "failed to delete '.git/worktrees/ABM-Service-Code-task23' / '...-v1.9.6-pointer': Permission denied" while pruning. Fetch exit was 0 and the refs were updated. The existing checkout's worktree metadata may be stale or locked; not touched.
- Observation 2: another worktree exists on the same branch: `C:/Users/juand/OneDrive/EFEX/EFEX GPT Work/ABM-Code-minors-14` at 39af8c1 [fix/task-14-minors]. Not touched by this run.
- Observation 3: scope was limited to the N1 change as instructed. The TASK-14 spec (origin/main docs/work-items/TASK-14.md) was not re-audited beyond its header; no spec conformance judgement is made here.

## Cleanup
- `git worktree remove --force "C:\Users\Admin\AppData\Local\Temp\abm-tester-14c"` exit 0. Worktree directory no longer exists. The existing checkout was only read (fetch and diff); no commits, pushes or ref/config changes by the Tester.

Verdict: PASS
