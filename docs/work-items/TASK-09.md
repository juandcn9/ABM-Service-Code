# Work item: TASK-09 — caller context, role/scope authorization, strict transport validation

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-09`; `INV-13`; `SEC-01` through `SEC-04`; `TEST-21` through `TEST-24` (parsing, authorization, and transport halves)
- Decision, gap, or risk records: `DEC-0004`, `RISK-0002`; no new decision or gap; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independently verified (see Independent verification)

## Scope

- Objective: parse the trusted caller context from headers, authorize every operation by role and exact account scope with a deny-by-default matrix, and provide strict transport helpers (exact fields, strict JSON, path/body account agreement).
- Included files/components: `src/abm/application/caller.py` (`CallerContext`), `src/abm/application/authorization.py` (`Operation`, `PERMISSIONS`, `authorize`), `src/abm/api/caller_context.py` (`parse_caller_context`), `src/abm/api/validation.py` (`strict_json`, `exact_fields`, `same_account`), `tests/security/test_caller_and_authorization.py`.
- Explicit exclusions: FastAPI routes, header extraction, and Pydantic models (`TASK-25`); the allowlisted deployment mode that refuses to start with caller-context trust disabled (configuration, `TASK-26`/`TASK-27`); database-backed checks such as cross-account movement substitution, which returns `MOVEMENT_NOT_FOUND` inside the transaction (`TASK-10` onward); safe-error and log rendering (`TASK-23`/`TASK-26`); health operations (`API-20`, `API-21`), which are unauthenticated and are not authorization operations.
- Dependencies and entry gate: `TASK-03` Verified. This branch also imports the `TASK-08` domain modules (identifiers, results, errors), so it is stacked on the `TASK-08` branch until PR #9 merges; the delivery-plan dependency table lists only `TASK-03`, and the stacking is a Builder choice to reuse that code instead of duplicating it.

## Acceptance evidence

- Focused tests (`pytest tests/security/test_caller_and_authorization.py`): missing, malformed (alphabet, length, whitespace, control, Unicode, percent-encoded, injection), duplicated-by-case, multi-valued, and binary headers all give `UNAUTHORIZED` with a message that leaks nothing; the role/operation matrix equals the Specs section 4 table exactly, with every API operation granted to exactly one role and every role/operation pair decided by the matrix; unknown and look-alike roles are denied; an `account_reader` is limited to its one trusted account (different, case-changed, padded, missing, or empty scope denied); a scope grants other roles nothing; all denials are the same generic `FORBIDDEN_SCOPE` value; path and body accounts must match byte for byte; bodies need exactly the allowed fields and a payload carrying caller fields is rejected; JSON with duplicate keys, `NaN`/`Infinity`, trailing text, invalid UTF-8, deep nesting, and over-long integers is refused; JSON floats and strings never become money. Mutation checks: removing the scope comparison or the duplicate-header check makes tests fail.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head, plus the same commands locally; import-boundary tests confirm `api` imports only `application`/`domain` and `application` only `domain`/`ports`.
- Failure, concurrency, authorization, and recovery cases: authorization is a pure function with no database access, so denial happens before any write transaction (`TEST-21`); concurrency and recovery are not applicable.
- Documentation/trace updates: README, CHANGELOG, this work item.

## Implementation notes

- Reversible technical choices and interpretations of the Specs:
  - An unknown role is a denial (`FORBIDDEN_SCOPE`, 403) because the OpenAPI role header is any opaque string and only a valid role can be authorized; a missing or malformed header is `UNAUTHORIZED` (401), per the OpenAPI response descriptions.
  - "Contradictory" context is implemented as the same header supplied twice (case-insensitively) or a multi-valued or non-string header. If the Specs intend more (for example a scope supplied to a role that never uses one), that is a GAP to raise before `TASK-23`.
  - The scope header is optional when parsing and required by authorization for account reads, because only reads use it.
  - Roles are matched exactly and case-sensitively against the matrix; `LEGAL-HOLD` is an operation id for the non-public `retention_controller` port, not an HTTP route.
  - Validation helpers raise `InvalidValue`; the boundary maps it to `VALIDATION_ERROR`. `authorize` and `parse_caller_context` return typed `Failure` values.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: PR #10, merged as `e3aada8` (it was stacked on `TASK-08` until PR #9 merged).
- Commands/checks and results: locally `pytest` 55 passed in this stacked branch, `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and both validators pass; CI results are on the PR.
- Review findings/resolution: Builder Audit `ponytail-review` (installed plugin 5.1.0, `full`, DV-01): one Should-fix, an over-long integer in a JSON body raised a plain `ValueError`; fixed with a test. Independent fresh-context review of head `977272c`: implementation correct (matrix equals both `specs/06` section 4 and every `x-authorized-role` in the OpenAPI), no Blocker; two Major test-evidence findings, resolved with tests only: F1 (the matrix test checked the granted set and uniqueness but not which role holds which operation, so moving `API-12` to `card_orchestrator` kept every test green) now compares each role's operations with an independent literal from the Specs; F2 (cross-account denial for the history read was untested and `ACCOUNT_SCOPED` was taken from the implementation) now asserts the scoped set literally and denies wrong, padded, case-changed, empty, missing, and absent accounts for history; both mutations now fail tests. F3 (stale test counts) corrected. F4 (non-text input to `strict_json` and non-mapping headers raised `AttributeError`) now give `InvalidValue` and `UNAUTHORIZED`. F5 (`1e999` becomes Infinity and a lone-surrogate escape cannot be encoded) now rejected. Observations carried to `TASK-25`: the adapter must pass one normalized string-keyed header mapping and must limit body size; an unknown role is a 403 (a reading of `specs/06` section 4, recorded above). Independently verified (see Independent verification).
- Residual risks: the header-to-context contract assumes a trusted ingress (`RISK-0002`); duplicate-key rejection depends on callers using `strict_json`, so `TASK-25` must route every body through it or an equivalent Pydantic setting; cross-account substitution and deployment-mode trust are not covered here.
- Next safe action: `TASK-10` after `TASK-06` (migrations, Code PR #8) and `TASK-07` are merged.

## Independent verification

- Role and context: Tester, fresh-context agents that did not build `TASK-09`, 2026-10-09. The sanitized report is committed at [`docs/evidence/TASK-09-tester-report.md`](../evidence/TASK-09-tester-report.md).
- Revision tested: Code PR #10 fix head `4161710816189ab271c867199155dea7a3103010`; the merged head `4598e06` (merge commit `e3aada8`) has an identical tree. Specs `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Result: PASS on re-verification of the fix head; the first review's two Major test-evidence findings and three smaller findings are resolved; zero Blocker. Tester Observation O1 (a `Mapping` that raises on iteration) is closed: see Minor closure (Stream B).
- Scope of "Verified": parsing of the trusted caller context, the deny-by-default role and account-scope matrix, and the strict transport helpers. `TEST-21` to `TEST-24` stay partly open for HTTP wiring, the deployment-mode trust check, cross-account movement substitution, and the "contradictory context" interpretation (`TASK-23`, `TASK-25`). `RISK-0002` (trusted ingress) is unchanged.
- Not verified: HTTP-level behavior (no routes exist); Python 3.12.15 locally.

## Minor closure (Stream B)

- Observation O1 (a `Mapping` that raises on iteration propagated): closed. `parse_caller_context` in `src/abm/api/caller_context.py` materializes the items inside a guard and returns `UNAUTHORIZED` on failure. Test: `test_a_mapping_that_raises_on_iteration_is_unauthorized_not_an_exception` in `tests/security/test_caller_and_authorization.py`.
