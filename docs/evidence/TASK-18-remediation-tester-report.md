# TASK-18 Tester report: final head c29f895

Date: 2026-10-12. Tester worktree: C:\Users\Admin\AppData\Local\Temp\abm-tester-18b (detached, removed at end).

## Pinned revision and chain

- origin/fix/task-18-fault-m09 = c29f8950ad0adbea14b886d23c8f8d34372ac54c (fetched with the specified refspec, moved from 7c820c9 to c29f895)
- parent of c29f895 = 7c820c957af6e565b874af2b91cf5547fc696a77 (7c820c9)
- parent of 7c820c9 = b81cee6df269ec8141377496634bb852fce8cb1f
- origin/main (`git ls-remote`) = b81cee6df269ec8141377496634bb852fce8cb1f, which matches
- Worktree HEAD before work: c29f895. HEAD after the mutation check: c29f895. Working tree after restore: clean (0 status lines).
- Diff 7c820c9..c29f895: 2 files, +15/-1. `tests/integration/test_fault_injection.py` (+14, new guard test) and `docs/work-items/TASK-18.md` (1 line, wording only: the "reverted" wording replaces "restored" in F2).

## Commands and exit codes (all in the tester worktree, Python 3.12.10 venv)

| Command | Exit | Result |
|---|---|---|
| `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock` | 0 | installed |
| `pytest -p no:cacheprovider -q` (full suite) | 0 | 1101 passed, 1 warning (StarletteDeprecationWarning in test_container_entry.py, benign), 320.76s. No failing tests, so no serial rerun was needed. |
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 175 files already formatted |
| `mypy src harness tests scripts` | 0 | Success: no issues found in 99 source files |
| `python scripts/validate_governance.py` | 0 | TASK-01 VALIDATION PASSED (11 required files, Specs pointer v1.9.12 / 1f6a26d) |
| guard test alone (`test_every_sql_writing_method_is_instrumented`) | 0 | 1 passed |

## Guard review

- Test at tests/integration/test_fault_injection.py:383-392. It collects the non-underscore callables of `sqlite_store.SqliteWriteTransaction` whose `inspect.getsource` matches the regex, and asserts the set equals `set(MUTATORS)`.
- Regex bytes checked with od: `re.search(r"\b(INSERT|UPDATE|DELETE)\b", ...)`. Exactly as specified, ASCII, no control characters.
- Passes on the real class (1 passed).

## Mutation check

- Backup taken (cmp verified). Removed the single MUTATORS line `"close_account",` (line 154) in the tester worktree only.
- Guard run: exit 1, FAILED at line 391. Assertion shows `'close_account'` in the computed writer set and missing from MUTATORS. The guard catches the regression that the earlier Tester pass (F3) showed the sweep could not catch.
- Restored by `cp` from backup (cmp verified, no git checkout). Guard re-run: exit 0, 1 passed. `git status --porcelain`: 0 lines.
- Note: a second `"close_account"` string remains at line 71 in a command table (not MUTATORS). It is unrelated to the guard, and the failure message confirms the guard keys on MUTATORS.

## Control-character check

- Bytes 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F: 0 occurrences in tests/integration/test_fault_injection.py and 0 in tests/integration/test_concurrency.py.
- Non-ASCII bytes in test_fault_injection.py: 0.

## Counts

- Full suite: 1101 passed, 0 failed, 0 errors, 0 skipped reported.

## Findings

- Blocker: 0
- Major: 0
- Minor (observation, not blocking): the guard is a source-text heuristic. It only detects write methods whose own source contains the literal keywords INSERT, UPDATE, or DELETE. It would not detect a write method that builds SQL in a helper or in another method, and it uses `vars(...)`, so inherited methods are not covered. It closes the F3 gap for the current class, and the current class is fully covered. Upgrade path if the write layer changes: have the write methods register themselves, or assert against the DB-level write log.
- Prior F3 (Minor, MUTATORS completeness with no guard): resolved by c29f895. Verified by the mutation above.

## Verdict

Verdict: PASS with findings
