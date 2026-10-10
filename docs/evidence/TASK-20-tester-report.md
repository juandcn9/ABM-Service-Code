# TASK-20 Tester report

**Verdict: PASS for the code** (Code PR #65, head `32450b8`, merged as `02d122f`). **The docs review failed on its first head** (`2b00cc3`, two Majors: a stale Specs pin and a stale closed-account decision). Both were corrected in the work-item revision `9db0ed8` (PR #64, merged `efd6c55`). No Blocker. Three Minors are scheduled.

## Subjects

- Code: `32450b8` on `feat/task-20-risk-restriction`. Files: `src/abm/application/risk.py` (new), `src/abm/persistence/sqlite_store.py`, `src/abm/ports/storage.py`, `tests/integration/test_risk_restriction.py` (new). No deletions.
- Specs: `v1.9.1`, `3a2e4b26070fc4d43bb52182991c72693c67fb7d`.
- Merged `main` differs from `32450b8` only by the Specs pointer PR #66 (v1.9.1). The feature code is identical to the tested head.

## Gate results (`32450b8`)

| Command | Exit | Result |
|---|---|---|
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 109 files already formatted |
| `mypy src harness tests scripts` | 0 | Success: no issues in 62 source files |
| `pytest -q` | 0 | 743 passed |
| `scripts/validate_governance.py` | 0 | Passed (on the v1.9.0 pointer of that head) |

## Spec-to-test trace

| Rule | Implementation | Test |
|---|---|---|
| API-17: `risk_controller` only | `authorize(..., RISK_RESTRICTION)` | `test_refusals_for_role_account_action_and_body` |
| API-17: account must exist | `ACCOUNT_NOT_FOUND` | same test |
| API-17: requested state must differ, stored `INVALID_TRANSITION` | state check in `risk.py` | `test_a_state_that_does_not_change_is_refused_without_effect` |
| Decision stored on set, NULL on clear (schema pair rule) | `set_restriction` | `test_set_blocks_...`, `test_clear_removes_...` |
| FR-10: no balance effect | no balance write | `test_set_blocks_...` (balance unchanged) |
| Response 200 `{account_id, restriction}` | `Response(200, ...)` | `test_set_blocks_...`, `test_clear_...` |
| One trace row per change | `append_trace`, `external_reference` = decision | `test_set_blocks_...` |
| Replay and conflict | `run_idempotent` | `test_exact_replay_...`, `test_same_key_with_a_different_request_...` |
| TEST-10: block refuses outgoing ACH, transfer, card authorization | existing gates | `test_block_refuses_outgoing_activity_and_permits_the_rest` |
| TEST-10: incoming credit, reads, correction permitted | existing and new paths | same test |
| DEC-0042: accepted on a closed account | no status check | **no test yet** (Minor 1) |

## Mutant results

| Mutant | Result |
|---|---|
| State-differs check removed | Caught (1 failed) |
| Clear keeps the old decision reference | Caught (2 failed; the schema pair rule raises an integrity error) |
| Set stops storing the decision reference | Caught (6 failed; the schema rejects a block with no reference) |

## Findings

- **Blocker:** none. **Major (code):** none.
- **Minor 1:** no test pins DEC-0042 (set and clear on a closed account). Owner Builder. Trigger TASK-21 (closure).
- **Minor 2:** outgoing ACH settle and return while the block is set are not tested, though the Specs permit resolution of accepted movements. Owner Builder. Trigger TASK-23.
- **Minor 3:** the clear-path trace row is not asserted. Owner Builder. Trigger TASK-23.
- **Docs, Major 1 and 2, and Minor 4:** corrected in `9db0ed8` (see above).

## Not verified

- The HTTP route and envelope for API-17 (TASK-25).
- The `idempotency.py` mapping of 409 `INVALID_TRANSITION` was not read line by line; the replay test covers the path.
- The docs revision was checked by the Builder, not by a second fresh-context reviewer.
