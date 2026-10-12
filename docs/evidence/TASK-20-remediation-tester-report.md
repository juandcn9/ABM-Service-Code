# TASK-20 independent Tester report (remediation of M-1)

## Pinned revision and chain
- Worktree: detached at `C:\Users\Admin\AppData\Local\Temp\abm-tester-20`, created from Code `5c9bfe4`.
- HEAD asserted equal to `5c9bfe4df1a8b8e8f9502439ea63a17cf48d0577` before and after all work.
- Parent chain: `5c9bfe4` (docs: remediation note wording) -> `ebff283` (test: TASK-20 card clearing and late clearing permitted under the block) -> `b81cee6` (Merge PR #122, docs/task-30-verified). `b81cee6` is an ancestor of `ebff283` (verified).
- origin/main: `git ls-remote https://github.com/juandcn9/ABM-Service-Code.git refs/heads/main` returned `b81cee6df269ec8141377496634bb852fce8cb1f`. The chain tip is origin/main's current commit, so the fix branch is based on current main.
- Note: the Code primary checkout is on `task-02-reproducible-toolchain` (bb539ae); it was not modified.

## Environment
- Python 3.12.10 venv at `.venv` in the worktree (gitignored).
- `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock`: exit 0.

## Commands and results (on 5c9bfe4)
| Command | Exit | Result |
|---|---|---|
| `python -m pytest -p no:cacheprovider -q` (full suite, one run) | 0 | 1020 passed, 1 warning (pre-existing StarletteDeprecationWarning in test_container_entry.py), 263.5 s. No failures, so no serial rerun was needed. |
| `python -m pytest ...::test_block_permits_clearing_of_authorized_card_movements_and_late_clearing` | 0 | 1 passed |
| `python -m pytest tests/integration/test_risk_restriction.py` (on mutant) | 1 | 1 failed (the new test), 8 passed |
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 175 files already formatted |
| `mypy src harness tests scripts` | 0 | Success: no issues found in 99 source files |
| `python scripts/validate_governance.py` | 0 | TASK-01 VALIDATION PASSED (Specs pointer v1.9.12 / 1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f) |

## Test verification (`test_block_permits_clearing_of_authorized_card_movements_and_late_clearing`)
Walked through the test body against the code:
- (a) Authorizes `mv-auth` (300) and `mv-rev` (300) before the block, both via `authorize_card` returning Success. Balance 1000 funded; holds 600.
- (b) `reverse_card` on `mv-rev` (releases its hold), then `set_block(uow)` sets `outgoing_blocked` with decision `dec-r1`.
- (c) `clear_card` on `mv-auth` returns Success with state `cleared` (asserted).
- (d) `clear_card` on the reversed `mv-rev` returns Success with state `late_cleared` (asserted).
- (e) Asserts balance 1000 - 300 - 300 = 400 and `restriction_of == ("outgoing_blocked", "dec-r1")`.
All five steps are present and match the test's assertions. The Builder's expectation matches the Specs (below).

## Specs lines relied on (Specs repo `ABM-Service-Specs` at pin `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f`)
- `specs/02-domain-and-invariants.md` section 7, line 102: "`outgoing_blocked` rejects new outgoing ACH, internal transfer, and card authorization; it allows incoming funds, required resolution of accepted movements (including clearing of an authorized card movement and a permitted late clearing, DEC-0031), returns, reversals, and approved corrections."
- `governance/decisions.md` DEC-0031: "Clearing of an authorized card movement, and a permitted late clearing, are required resolution of accepted movements and are not blocked by the `outgoing_blocked` restriction. ... the restriction still rejects new card authorizations." (Approved, JDC, 2026-10-10, option A.)
- `specs/02` lines 92-94 (card state rules): authorized_with_hold -> cleared with one debit and hold released; reversed/expired -> late_cleared posts exactly one debit with no active hold to release. Matches the test's expected balance (400) and the absence of any hold mutation for the late clearing.
- `specs/08-verification.md` TEST-10 (line 34): "Risk restriction blocks outgoing ACH, transfers, and card authorization but permits incoming credit, reads, and correction."
- DEC-0042 is out of scope for this remediation; not re-tested here.

Conclusion: clearing under the block is permitted by specs/02 section 7 and DEC-0031. The assertions match the Specs, not just the Builder's expectation.

## Mutation check
- Scratch edit (in the worktree only): added to `clear_card`'s `work()` in `src/abm/application/cards.py`, after the ACCOUNT_NOT_FOUND check, `if account.restriction != "none": return failure("OUTGOING_BLOCKED", ...)`.
- Result: the new test failed at the `cleared` assertion (`assert isinstance(cleared, Success)`); 8 other tests in the file passed. The mutation is detected.
- Reverted with `git -c safe.directory=* checkout -- src/abm/application/cards.py`. `git status --porcelain` is empty; HEAD is still 5c9bfe4.

## Work-item check (`docs/work-items/TASK-20.md`, Remediation section)
- Test name, file path, scenario (authorize + reverse before block, clear -> `cleared`, late-clear -> `late_cleared`), balance 400, and block still set: accurate.
- "Mutation ... makes the test fail": confirmed.
- "tests/integration/test_risk_restriction.py 9 passed; ruff, mypy pass": confirmed (9 tests in the file; ruff and mypy exit 0).
- "Full-suite run and fresh Tester pass on the fix head are pending": now stale. The full suite was run here (1020 passed) and this report is the fresh Tester pass. The line should be updated by the Builder.

## Findings
- **Blocker:** none.
- **Major:** none. Open M-1 from efd6c55 is resolved by the test (fails on the mutant, passes on the source).
- **Minor 1 (docs, stale):** the Remediation section still says the full-suite run and fresh Tester pass are "pending" (line 63). They are now done on this revision (1020 passed; this Tester pass).
- **Minor 2 (docs, stale pin):** the work item's Authority line (line 7) still pins Specs `v1.9.1` / `3a2e4b2...`, while `validate_governance.py` reports the Code pointer as `v1.9.12` / `1f6a26d...`. Not part of the remediation section, and the work-item pin records the Specs the item was written against. A prior Tester rated stale Specs pins Major on TASK-20, so the Builder or JDC should decide whether to refresh it.
- **Minor 3 (test coverage, optional):** the new test asserts the final balance and state, but does not assert that the cleared movement's hold is released (held balance) or that the late clearing created no hold. The Specs (specs/02 lines 92-94) require both. Current assertions would not catch a regression in hold release on clearing. Optional follow-up.

## Verdict
Verdict: PASS with findings
(Open Blocker: 0. Open Major: 0. Minor: 3.)
