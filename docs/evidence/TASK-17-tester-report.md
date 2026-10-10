# TASK-17 independent Tester report (sanitized record)

**Provenance:** a fresh-context reviewer and Tester agent, read-only, run on 2026-10-10 against Code PR #53 at head `5bf80f8a84d9c05426d908eeb8dcfd343392c790`. The merge to `main` (`00e45c6`) has an identical tree (`ff73429e2f0386e1186c75a13a955cdfa7f02443`), so the result applies to the merged revision.

**Pinned Specs:** `v1.8.3` / `c24abb2b31f0969c8e8c6eee24d9187a52df6c0b`.

## Scope tested

- Added: `tests/integration/test_idempotency_conformance.py` (98 tests, a 16-scenario table). No source change.
- Covers every command group in `docs/work-items/TASK-17.md`: registration; incoming ACH notice, settle, return; outgoing ACH create, submit, settle, reject, cancel, return; internal transfer; card authorize, clear, reverse, expire, refund. Each command runs a success and a rejection scenario.
- Asserts exact status and body, the replay flag, no writes on replay or conflict, and that the stored outcome is unchanged. The 500 and 503 cases use injected faults and check that no outcome is stored and a retry runs fresh. Reads store nothing.

## Gates

| Gate | Result |
|---|---|
| `mypy src harness tests scripts` | exit 0, 55 source files clean |
| `pytest -q -p no:cacheprovider` | exit 0, 709 passed (98 new) |
| `ruff check .` | passed |
| `ruff format --check .` | exit 0, 97 files formatted |
| `scripts/validate_governance.py` | passed, pin `v1.8.3` / `c24abb2` |

## Mutation checks (applied to copies, then removed)

| Mutant | Result | Killing tests |
|---|---|---|
| A1: replay branch replaced by fresh execution (`idempotency.py`) | 32 of 32 replay cases failed | e.g. `test_replay_and_conflict_store_and_return_exactly_one_outcome[register_account-success]` |
| A2: replay branch replaced by `IDEMPOTENCY_CONFLICT` | 32 of 32 failed | e.g. `[register_account-rejection]` |
| B: `amount_cents` dropped from the internal transfer fingerprint (`transfers.py`) | caught | `[internal_transfer-success]`, `[internal_transfer-rejection]` (conflict assertion) |

## Findings

- Blocker: none. Major: none.
- Minor 1 (scheduled): the 401 non-stored status has no test. 400 and 403 are covered (`test_pre_idempotency_failures_are_not_stored`), and 500 and 503 are covered. 401 is an edge-level check. Owner: Builder. Trigger: a follow-up in TASK-17 or the edge work.
- Minor 2 (documentation): the work item status was still Draft on `main` before this record. Corrected in the same documentation change.

## Design note

- Registration scope is the customer identifier (`specs/02`), so a changed customer under the same key is a new scope. The conflict case for registration therefore changes the instruction identifier. This matches the Specs; it is not a mismatch.

## Not verified

- ACCOUNT_CLOSED cases in the conformance table: closure is TASK-21.
- SQLITE_BUSY in this table: covered by the registration tests.
- Production readiness: outside this task.
