# TASK-22 Tester report, pass 1

**Verdict: conditional PASS on head `07d12eb`** (Code PR #74). Two Majors, both resolved before the merge of PR #74: Major 1 by tests (in `caacace`), Major 2 by DEC-0047 (a Specs decision, not a code change). Stored as its own record because the merge rule requires review evidence before merge. This record was committed after the merge (see the process record in the TASK-22 work item).

## Subjects

- Code: `07d12ebe3ee60a490d21d5bdefa1121bf2afe7c0`, branch `feat/task-22-retention`, base `main` at `0ab745d`. One commit, 10 files, +490 lines.
- Docs: PR #73, head `91c3f30ed1d80abbaedc8383f4f4d65c818a2587` (superseded; merged head `693d1b458cc16c83a3cf680e0c2472edf47b5175`), file `docs/work-items/TASK-22.md`.
- Specs: tag `v1.9.3`, `e72391c0f53d678c6e013cc0f1d9808f730994fa`.

## Gate results (`07d12eb`)

The file count is ruff's own count of the files it checked; the tree holds 69 `.py` files, and that count (not ruff's) is the reproducible figure.

| Gate | Command | Exit | Result |
|---|---|---|---|
| Lint | `python -m ruff check .` | 0 | All checks passed |
| Format | `python -m ruff format --check .` | 0 | ruff reports all checked files as formatted (ruff's count: 118) |
| Types | `python -m mypy src harness tests scripts` | 0 | 67 source files, no issues |
| Tests | `python -m pytest -q` | 0 | 765 passed |
| Governance | `python scripts/validate_governance.py` | 0 | Passed (Specs pointer v1.9.3) |
| Targeted | `python -m pytest -q tests/integration/test_retention.py` | 0 | 10 passed |

## Findings

1. **Major: late-event advances untested.** Only the incoming return advance had a test. Mutant: removing the card refund's advance call passed the suite. Fixed in `caacace` with `tests/integration/test_retention_late_events.py` (outgoing return, correction, card late clearing, card refund).
2. **Major: legal-hold refusals had no approved trace.** The requested-state rule (`INVALID_TRANSITION`, stored), and the stored `ACCOUNT_NOT_FOUND`, were not in Specs v1.9.3. Resolved by JDC as DEC-0047 (Specs PR #39, merged `f4f4f20`, tag `v1.9.4`).
3. **Minor: same-key replay of a stored `INVALID_TRANSITION` not asserted.** Fixed in `caacace` (`tests/integration/test_legal_hold_rules.py`).
4. **Minor: wrong `record_type` not tested.** Fixed in `caacace` (same file).
5. **Minor: work item cited `specs/03` section 4 for the retention-controller row.** The row is in section 8. Fixed in PR #73.
6. **Minor, pre-existing on `main`: README stated Specs `v1.9.0`.** Not caused by TASK-22. Scheduled.

## Mutants (pass 1)

| Mutant | Result |
|---|---|
| Delete `finalize` in `cards.py` refund | Not caught (fixed by the late-event tests) |
| `RETENTION_YEARS = 7` changed to `13` | Caught |
| Remove the legal-hold clause from `evaluate` | Caught |
| Remove the requested-state check in `legal_hold.py` | Caught |

## Not verified (pass 1)

- No HTTP route exists in this tree, so TEST-37 holds only at application level.
- The February 29 mapping was tested for one target year only.
- Clock regression (`finalize` overwrites the dates without a monotonic check) was not tested.
- Concurrency and fault injection were not run.
