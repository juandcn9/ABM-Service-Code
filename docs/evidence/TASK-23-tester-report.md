# TASK-23 Tester report

**Verdict: PASS on the approved head `114599e`** (Code PR #79, merged as `c04a8cc`; the merged tree equals the tested tree). Scope is the application and persistence security-negative facets of DEC-0051. The HTTP, structured-log and metric, runtime-correlation, and evidence-bundle facets belong to TASK-25, TASK-26 and TASK-34 and are not claimed here. TEST-29 is not claimed.

## Passes

1. `b6938157`: PASS with three Minor test-strength findings. Two were fixed in later commits: a rollback-after-write test, and a non-sqlite exception kind in the fault sweep. The third (a module-local, fixed-verb scan for TEST-20) is recorded as a limit below.
2. `c211df5`: PASS (fresh-context re-check after the Minor fixes; mutants caught).
3. `114599e`: PASS, fresh-context review, exact approved head. No Blocker or Major. This record is the review for the merge.

## Head evidence (`114599e`)

- Specs: `v1.9.6`, commit `112a03bca76e53fcf4a57098318121d89ca507e5`.
- Changes against `main`: validator additions, a read- and write-side safe-error mapping, substitution and unsupported-operation tests, scheduled TASK-19 to TASK-22 cases, and a changed read-transaction test.

## Gates (`114599e`)

| Command | Exit | Result |
|---|---|---|
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 127 files already formatted (ruff's own count) |
| `mypy src harness tests scripts` | 0 | 72 source files, no issues |
| `pytest -q` | 0 | 789 passed |
| `scripts/validate_governance.py` | 0 | Passed (Specs v1.9.6) |

CI on the exact head: quality-gates and validate-governance passed.

## Facet trace (DEC-0051, TASK-23 rows)

| Facet | Test |
|---|---|
| Authorization, TEST-21 and TEST-22 | `tests/security/test_caller_and_authorization.py` |
| Cross-account substitution, TEST-23 | `tests/security/test_unsupported_and_substitution.py::test_a_movement_of_another_account_is_refused_exactly_like_a_missing_one` |
| Unsupported operations, TEST-20 application part | `tests/security/test_unsupported_and_substitution.py::test_no_application_operation_updates_deletes_or_reopens` |
| Identifiers, TEST-24 application part | `tests/unit/test_identifiers.py` |
| Injection as data, TEST-25 | `tests/security/test_sql_static_scan.py` and integration injection cases |
| Prohibited data in the current repository, TEST-26 current-artifact part | `tests/security/test_governance_validator.py` (including the repository-passes test and the new mutation cases) |
| Safe application errors, TEST-28 application part | `tests/integration/test_fault_injection.py` (generic and plain kinds); `tests/integration/test_reads.py::test_unexpected_failure_in_each_read_is_safe_and_ends_the_snapshot`; `tests/integration/test_rollback_after_write.py` |
| Immutable records, TEST-30 | `tests/integration/test_readiness.py`, `tests/integration/test_migration_protections.py` |
| Baseline required secrets, TEST-27 | Cited from TASK-02 evidence (`docs/work-items/TASK-02.md`) and the validator scan of `.env.example`. No executable missing-secret assertion, because no required secret exists. |

## Mutants (`114599e`)

| Mutant | Result |
|---|---|
| Read path: remove the `INTERNAL_ERROR` mapping | Caught (3 failed in `test_reads.py`) |
| Validator: disable the secret-pattern check | Caught (11 failed) |
| Write path: change the rollback mapping | Caught (1 failed) |

## Findings

- **Blocker:** none. **Major:** none.
- **Minor 1:** TEST-27 is a citation, not a new executable assertion. Accepted under DEC-0051.
- **Minor 2:** the broad `except Exception` mapping hides programming errors from the logs until TASK-26 provides structured logging. Accepted as a limit with a named upgrade path.
- **Limit (TEST-20):** the no-verb scan covers only functions defined in each application module, and only the verbs it lists. The HTTP route check is TASK-25.

## Not verified

- HTTP routes, envelopes, and correlation IDs (TASK-25 and TASK-26).
- Structured logs, metrics, and runtime redaction (TASK-26).
- The evidence-bundle facet of TEST-26 (TASK-34).
- A second platform or a flakiness re-run.
