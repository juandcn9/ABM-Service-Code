# TASK-19 Tester report

**Verdict: PASS** (no Blocker, no Major; three Minors scheduled below)

## Subject and head

- Feature commit `0feb40a` (`feat: TASK-19 approved corrections (API-16, FR-09)`), tree `9b59fa9ea5bb8d6940ad9a420f589643204414be`.
- Merged on `main` as `5d2cc58` (PR #62). The tested tree equals the merged tree.
- Work item: `docs/work-items/TASK-19.md` (PR #61, merged `64b112a`).
- Specs: `v1.9.0`, `5fcb90503ab38bbc1eb29fdcf7505767d842acb2`.

## Gate results (exact head `0feb40a`, project venv Python)

| Command | Exit | Result |
|---|---|---|
| `python -m ruff check .` | 0 | All checks passed |
| `python -m ruff format --check .` | 0 | 105 files already formatted |
| `python -m mypy src harness tests scripts` | 0 | Success: no issues found in 60 source files |
| `python -m pytest -q` | 0 | 735 passed |
| `python scripts/validate_governance.py` | 0 | Validation passed; Specs pointer `v1.9.0` |

## Spec-to-test trace

| Rule | Implementation | Test | Status |
|---|---|---|---|
| FR-09, TEST-09: approved correction appends one linked entry; no existing record changes | `src/abm/application/corrections.py`: one `correction` ledger entry, one movement, one trace row | `test_credit_correction_appends_one_linked_entry_and_keeps_history`, `test_debit_correction_may_make_the_balance_negative` | Covered for the ledger prefix. The original movement and trace rows are not asserted unchanged (M-3). |
| API-16: `correction_authority` only | `authorize(..., Operation.CORRECTION)` | `test_other_roles_and_extra_fields_are_refused` | Covered |
| API-16 / DEC-0026: reused `correction_id` is `INVALID_TRANSITION` (409), stored | `correction_id` reuse check | `test_reused_correction_id_is_refused_without_effect` | Covered |
| One correction per decision (specs/03) | `decision_reference_taken` check inside the serialized write transaction | `test_reused_decision_is_refused_without_effect` | Covered. No database UNIQUE index, as the work item states. |
| specs/05 field map, DEC-0028 | `decision_reference` on the movement; `correction_of_entry_id` on the entry | `test_credit_correction_...`, `test_correction_may_name_a_corrected_entry_on_the_same_account` | Covered |
| TEST-10: correction permitted under a risk restriction | No restriction check on the correction path | `test_debit_correction_may_make_the_balance_negative` (restriction set by SQL) | Covered for the correction part. Incoming credit and reads under restriction belong to TASK-20. |
| INV-10: correction may make the current balance negative | `apply_balance` with no floor | debit test expects -800 | Covered |
| INV-17: replay and conflict | `run_idempotent` | `test_exact_replay_...`, `test_same_key_with_a_different_request_...` | Covered |
| INV-16: closed-account corrections accepted | No status check (correct for TASK-19) | none | Deferred to TASK-21 |

## Mutant results

Three mutants were applied one at a time to a self-contained copy. Each was caught by a correction test.

| Mutant | Caught by |
|---|---|
| Debit sign reversed | `test_debit_correction_may_make_the_balance_negative` |
| Decision-reuse check removed | `test_reused_decision_is_refused_without_effect` |
| Corrected-entry same-account check removed | `test_corrected_entry_of_another_account_or_unknown_is_refused` |

## Findings

- **Blocker:** none.
- **Major:** none.
- **M-1 (Minor): explicit null `corrected_entry_reference` is accepted.** The contract types the field as a string, not nullable. A null value returns 201 with no financial effect. Scheduled: Builder, trigger TASK-25 (HTTP binding and exact envelopes).
- **M-2 (Minor): no committed test for replay of a stored 409.** Probed by hand: a replayed `INVALID_TRANSITION` returns the stored outcome with no second effect. Scheduled: Builder, trigger TASK-23 (negative and unsupported-operation tests).
- **M-3 (Minor): test gaps.** The original movement and trace rows are not asserted unchanged. No correction-level test for amount 0, amount above the maximum, or a non-USD currency; the shared validators have unit tests. Scheduled: Builder, trigger TASK-23.

## Not verified

- The HTTP route for API-16 (TASK-25).
- Closed-account corrections (INV-16, TASK-21).
- Incoming credit and reads under restriction (TEST-10, TASK-20).
- Two racing writers creating corrections for one decision. The code relies on the serialized write transaction; no multi-connection test exists for this task.
