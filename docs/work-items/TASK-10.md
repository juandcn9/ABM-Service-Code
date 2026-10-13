# Work item: TASK-10 — transactional idempotency foundation and account registration

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-10`; `BT-09`; `FR-01`, `FR-15` (registration slice); `INV-02`, `INV-03`, `INV-06`, `INV-17`; `API-01`; `DATA-01`, `DATA-05`, `DATA-06`, `DATA-07`; `TEST-01`, `TEST-15` and `TEST-16` (registration slice)
- Decision, gap, or risk records: `DEC-0011`, `DEC-0012` (retention row); no new decision or gap; Specs observation on the scope column (see Implementation notes); DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: one reusable transactional idempotency runner that every later state-changing instruction will use, the first storage ports, and account registration on top of it.
- Included files/components: `src/abm/ports/storage.py` (storage ports and `StorageFailure`), `src/abm/application/idempotency.py` (`run_idempotent`, `scope_key`, storable rejections), `src/abm/application/registration.py` (`register_account`, `RegisterAccount`), `src/abm/persistence/sqlite_store.py` (SQLite unit of work and write transaction), `Failure.replayed` in `src/abm/domain/results.py`, and `tests/integration/test_registration.py`.
- Explicit exclusions: the FastAPI route, header extraction, and response envelope with `meta` (`TASK-25`); account reads and history (`TASK-11`); movements, holds, ledger entries, and every other command (`TASK-13` onward); structured safe rejected-request security evidence and logging (`TASK-26` under DEC-0051); readiness checks that registrations have traces (`TASK-12`); closure and restriction.
- Dependencies and entry gate: `TASK-07` (connection and transaction unit), `TASK-08` (domain values and results), `TASK-09` (caller context and authorization). Those are open PRs (#8, #9, #10, and the `TASK-07` branch); this branch contains them by merge and its PR is opened after they are merged into `main`, so its diff shows only `TASK-10`.

## Acceptance evidence

- Focused tests (`pytest tests/integration/test_registration.py`, real SQLite files): registration creates exactly one open, zero-balance USD account with one retention row (null dates, no legal hold), one accepted `register_account` trace, and one stored success outcome, and no movement, hold, ledger, or evidence row (`TEST-01`, `INV-03`); the same key and request replays the original outcome with `replayed` true and creates no row even after time has advanced; a duplicate account or customer is rejected with `DUPLICATE_ACCOUNT` (409), stores only the deterministic rejection, and creates no business row; a stored rejection replays exactly; a new key for the same registration is a new duplicate, not a replay; a changed request under the same key returns `IDEMPOTENCY_CONFLICT` with no write and leaves the original outcome intact; unauthorized roles never reach storage; invalid bodies and keys (missing or extra fields, caller fields in the body, wrong currency, bad identifiers, non-string keys) give `VALIDATION_ERROR` and store nothing; a failing clock gives `SERVICE_UNREADY` with no effect; failure injected before each of the five storage calls leaves all tables empty and the same request then succeeds (`TEST-16`, `INV-06`); a transient failure returned by the work is rolled back with its effects and not stored; a busy database gives retryable `SERVICE_BUSY` and stores nothing; six concurrent registrations of one customer produce exactly one account (`INV-02`); scope keys are deterministic and fit the stored alphabet. Mutation checks: removing the fingerprint comparison or the duplicate check makes tests fail.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head; the import-boundary tests confirm `application` imports only `domain` and `ports`, and `persistence` only `domain` and `ports`; the SQL static scan covers the new store (fixed statements, bound values).
- Failure, concurrency, authorization, and recovery cases: covered above; restart and idempotent replay across a process restart belong to `TASK-28`.
- Documentation/trace updates: README, CHANGELOG, this work item.

## Implementation notes

- Reversible technical choices:
  - The runner takes the instruction as a callback `work(tx, now)`; a `Failure` returned from it must come before any write. A storable rejection (the nine codes the `idempotency_outcomes` CHECK allows) is stored as a deterministic outcome; any other failure aborts the transaction, so nothing is stored and the request is re-evaluated (`DEC-0011`).
  - The stored body is `{"ok": true, "data": ...}` or `{"ok": false, "error": {code, message, retryable}}` without `meta`; the API edge adds `correlation_id` and `replayed` so a replay differs only in metadata.
  - The registration fingerprint covers all five request fields including `instruction_id`; the same key with a different `instruction_id` is a conflict. If the Specs intend otherwise that is a GAP to raise before `TASK-13`.
  - Authorization runs before body or key validation and before any storage access, so an unauthorized caller learns nothing about validity.
  - Storage ports are defined here, the first task that needs them, and grow with each aggregate; `SqliteUnitOfWork.write()` maps driver errors to a safe `StorageFailure` carrying the `Failure` from `to_failure`.
- Specs observation (for the Updater, not a Code defect): `specs/02` defines the idempotency scope as `customer_id + registration` and `account_id + operation`, but the schema limits the stored scope to 128 characters of `[-A-Za-z0-9._~]`, which two 128-character identifiers cannot fit. Code stores the SHA-256 hex digest of the pair (`scope_key`), which is deterministic, unambiguous, and within the alphabet; replays and conflicts behave as specified. If the Specs prefer another encoding, only `scope_key` changes (a new migration is not needed because no data exists yet).
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record; the PR is opened after the `TASK-06` through `TASK-09` PRs merge.
- Commands/checks and results: locally `pytest` 434 passed in this branch after merging `main` (includes the merged `TASK-06` to `TASK-09` tests), `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and both validators pass.
- Review findings/resolution: Builder Audit `ponytail-review` (installed plugin 5.1.0, `full`, DV-01) found nothing further to fix. A fresh-context review and Tester verification of the final head are still required.
- Residual risks: `work` callbacks must return a `Failure` only before writing, which is enforced by convention and by the abort path for non-storable failures but not for storable ones (a later task should add a savepoint if an operation needs to reject after partial work); the safe rejected-request security evidence for deterministic rejections is not emitted yet; replay across a real restart is untested until `TASK-28`.
- Next safe action: `TASK-11` (account reads and trace sequencing) and `TASK-12` (startup and readiness) after this PR is merged.

## Carried to later tasks (review of PR #14)

- `TASK-25` (API edge): `run_idempotent` lets unexpected exceptions from the instruction propagate after rollback. The edge must map them to the safe `INTERNAL_ERROR` response that `specs/04` requires.
- Scope key label: the stored scope hashes `register_account` as the operation name, while the Specs pair is `customer_id` + `registration`. Internal and deterministic; recorded here so the Updater can confirm the label.

## Independent Tester evidence

- Revision: merge `17ffbcf`. Report: [`docs/evidence/TASK-10-tester-report.md`](../evidence/TASK-10-tester-report.md).
- Result: PASS with findings: 0 Blocker, 0 Major, 3 Minor. Status stays Implemented until the Major findings are resolved.

## Verified record

- Tester PASS on the merged revision `17ffbcf` (PR #14, `main`), with Blocker 0, Major 0, Minor 3: `docs/evidence/TASK-10-tester-report.md`. The earlier "review and Tester still required" wording in Completion is superseded by this pass.
- Scheduled items, each with an owner and a trigger:
  - Safe rejected-request security evidence is not emitted for deterministic rejections (`specs/04` API-01). Owner Builder. Trigger: TASK-25 (API edge). Tester Minor 1.
  - Unexpected exceptions from the instruction propagate out of `run_idempotent` without a safe `INTERNAL_ERROR` mapping. Owner Builder. Trigger: TASK-25 (API edge). Tester Minor 2.
  - "Failure only before writes" is a convention, not enforced, for storable rejections. Owner Builder. Trigger: the first task that adds a storable rejection after a write. Tester Minor 3.

## Minor closure (Stream B)

- Absent versus null in the fingerprint (TASK-08 O3, TASK-10): the rule in `src/abm/domain/fingerprint.py` is that an absent field and a null field produce different fingerprints, and each operation passes a fixed field set. Test: `test_an_absent_field_and_a_null_field_have_different_fingerprints` in `tests/unit/test_results_and_fingerprint.py`. The Specs do not state this rule; it is the code's rule, recorded here.
- Registration has no optional nullable field, so no registration fingerprint changed.
