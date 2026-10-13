# TASK-12 independent Tester report, head `0cf87ee` (merged as `0ba2fc4`)

**Provenance:** fresh-context Tester agent, read-only, detached worktree at the pinned SHA, run on 2026-10-13. The Tester made no commits, refs or config changes and removed its worktree afterwards. This record is the Tester's reported result; the raw session transcript is not committed.

**Subject:** branch `fix/task-12-majors`, head `0cf87ee` (PR #148), merged as `0ba2fc4`. The branch carries the finalized-state checks (Tester Major M2, commit `c56018f`), the work item citing DEC-0078, DEC-0082 and DEC-0083 (`81c1e9d`), and a merge of `origin/main` at `1599ec4` (`0cf87ee`) that cleared the earlier base-lag Minor. Earlier fresh-context Tester on `81c1e9d`: PASS, Blocker 0, Major 0, Minor 1 (the base lag; cleared by the merge).

## Merge check

- `git diff 1599ec4 0cf87ee -- src/`: only `readiness.py` changes, from the TASK-12 commits.
- `git diff 81c1e9d 0cf87ee -- src/`: empty. The merge added only `main`'s TASK-16 docs and tests.

## Gates

Python 3.12.10, existing project venv (no installs).

| Gate | Result |
|---|---|
| `scripts/validate_governance.py` | passed |
| `ruff check` | all checks passed |
| `ruff format --check` | 187 files formatted |
| `mypy src harness tests scripts` | no issues in 101 files |
| `pytest --collect-only -q -p no:cacheprovider` | 1317 collected |
| targeted pytest, 14 files (`test_readiness`, `test_database`, `test_migrations`, `test_migration_protections`, `test_migration_runner_edges`, `tests/unit/test_recovery_claims`, `test_cards`, `test_closure`, `test_fault_injection`, `test_outgoing_ach`, `test_incoming_ach`, `test_transfers`, `test_http_slice1`, `test_http_slice2`) | 595 passed; one Starlette httpx deprecation warning, not a failure |
| full pytest suite | not run (known stall on the review host in `test_concurrency.py`; CI is the authority for the full suite) |

## Finalized-state predicates (specs/05 section 5, DEC-0083)

- Rule (a): a movement in a hold-only terminal state (`reversed`, `expired`, `rejected`, `cancelled_before_submission`) has no ledger entry. `late_cleared` is excluded. Reviewed: matches the rule.
- Rule (b): a finalized hold (state not `active`) cites evidence with the same `movement_id`. NULL evidence is flagged. Reviewed: matches the rule.
- A legitimate late clearing after an expired hold is ready (`test_a_late_clearing_after_an_expired_hold_is_ready`). The hold state `released` matches the expiry path in `cards.py`.

## Mutation checks

Each mutant was applied in a Tester-owned copy, the test file was run, and the source was reverted from a saved copy with SHA-256 verified. `src/` was clean afterwards.

| Mutant | Result in `test_readiness.py` |
|---|---|
| hold-only terminal-state ledger rule disabled | 1 failed, 72 passed (baseline 73 passed) |
| evidence-binding rule disabled | 1 failed, 72 passed (baseline 73 passed) |

## Findings

- Blocker: 0
- Major: 0
- Minor: 0

Verdict: **PASS** for the TASK-12 implementation at `0cf87ee`: no open Blocker, Major or Minor finding.

## Not verified

- The full pytest suite on this head (see Gates).
- The scheduled items in the TASK-12 work item (closure ordering of same-second effects; the section 5 rules beyond the two above). They are not findings of this pass; each has an owner and a trigger there.
