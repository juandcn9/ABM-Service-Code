# TASK-18 independent Tester report (sanitized record)

**Provenance:** fresh-context reviewer and Tester agents, read-only, run on 2026-10-10 against Code PR #57 at head `93370daf0dcb721dbe5fe93d9fdaaff949693bbd`, then re-run on the merged head `da05269ffc7c14070e7d0218e2e00301388acf57` (which adds only a merge of `main`; the three test files are byte-identical). Merged to `main` as `2eb7a4c` (merge commit).

**Pinned Specs:** `v1.8.4` / `618a7eb5ac1707ac99fea845562ec39afd124f0a`.

## Scope tested

- Added: `tests/integration/test_concurrency.py`, `tests/integration/test_fault_injection.py`, `tests/integration/store_support.py`. No source change.
- Covers TEST-14 (two concurrent debits: at most one success, no negative available balance), TEST-36 (at most one ledger effect and one evidence item per movement and effect kind across races, with the settlement and return pair and the clear and refund pair allowed), TEST-38 (busy, disk-full and simulated faults: safe failure, no partial effect), and the section 6 barrier protocol and section 7 rollback sweep.
- Concurrency uses independent connections and a barrier; no sleep-based assertions.

## Gates (venv python, `-I`)

| Gate | Result |
|---|---|
| `mypy src harness tests scripts` | exit 0, 58 source files |
| `pytest -q -p no:cacheprovider` | exit 0, 724 passed (15 in the new files) |
| `ruff check .`, `ruff format --check .` | exit 0 (101 files formatted) |
| `scripts/validate_governance.py` | exit 0, pin `v1.8.4` / `618a7eb` |

## Mutation checks (applied to copies, then removed)

| Mutant | Result | Killing tests |
|---|---|---|
| `write_transaction` commits on error (`database.py`) | killed | the rollback sweep (`test_a_fault_at_any_write_or_before_commit_leaves_the_pre_command_snapshot`, 6 cases), the three rollback tests in `test_database.py`, and the storage-fault tests of each command group |
| No available-funds check in the internal transfer (`transfers.py`) | killed | the two-debit race tests (transfer vs transfer, transfer vs outgoing hold) and the insufficient-funds tests |
| Outgoing settlement evidence guard dropped (`outgoing_ach.py`) | survived | none: the state check runs first, so the guard is unreachable in these races |

## Findings

- Blocker: none. Major: none open.
- Minor 1 (scheduled): the outgoing settlement evidence guard is not distinguished by the TEST-36 races (the mutant survives). Owner: Builder. Trigger: TASK-18 follow-up.
- Minor 2 (scheduled): the M09 mutant (deferred `BEGIN`) is not named by the new tests; its only detector is the TASK-06 migration test. Owner: Builder. Trigger: TASK-18 follow-up.
- Minor 3 (stated limit): the subprocess kill lands after the first balance update, not during COMMIT; faults are simulated `sqlite3` errors, not real disk-full. Owner: Builder. Trigger: a later hardening task.
- Minor 4 (code hygiene): a `list[object]` with `type: ignore` in `test_concurrency.py`, a hard-coded mutator list in `test_fault_injection.py`, and a CRLF comment. Owner: Builder.
- Process note: the first merge of `main` into the branch briefly removed the TASK-18 work item from the PR diff (the branch predated PR #56). This was corrected by merging `main`; the diff is the three test files only.

## Not verified

- Winner order is not asserted per run; both orders are exercised by repetition, not guaranteed.
- Production concurrency, scale, or real disk-full behaviour: outside this task (DEC-0003).
- Backup and restore: outside this task.
