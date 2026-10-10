# Work item: TASK-23 — application and persistence security-negative evidence

**Status:** Ready for JDC review

## Authority

- Specs version and exact SHA: `v1.9.6` / `112a03bca76e53fcf4a57098318121d89ca507e5`.
- TASK and affected IDs: `TASK-23`; `DEC-0051`; `SEC-01` through `SEC-12`; application/persistence contributions and predecessor evidence for `TEST-20` through `TEST-30` as assigned in Specs `08-verification.md` section 3.1.
- Decision, gap, or risk records: `GAP-0003`, resolved by `DEC-0051`. No requirement, security control, or release gate is waived.
- Owner: Builder (Claude Code); independent fresh-context review of the exact PR head is required. JDC alone approves and merges.
- Dependencies and entry gate: `TASK-09` and `TASK-19` through `TASK-22` are Implemented. Code points to the approved immutable Specs release above.

## Scope

- Complete the application/persistence security-negative suite for artifacts available through TASK-22: unsupported operations, authorization and scope enforcement, cross-account substitution, strict identifiers and command validation, parameterized SQL, current-artifact prohibited-data scanning, safe application errors, immutable-record protection, readiness corruption detection, and exact no-effect behavior.
- Map unexpected write and read adapter failures to safe `INTERNAL_ERROR`; every read snapshot ends without leaking exception, SQL, or path detail.
- Exercise every movement-bearing command against foreign and missing movements with indistinguishable failures and no state change.
- Close scheduled TASK-19 through TASK-22 test gaps: stored-409 replay, correction immutability and money validation, restriction-resolution cases and clear trace, submitted-closure blocker, closed-account incoming settlement, isolated post-closure readiness, and the retention-test description.
- Expand the repository validator from secret/card detection to high-confidence email, phone, government-identifier, and prohibited personal/bank-field patterns, with mutation tests.

## Shared TEST evidence and exact later owners

| TEST | TASK-23 evidence | Exact later finalizer |
|---|---|---|
| TEST-20 | Application exports contain no delete/update/reopen/balance-setter operation; unsupported attempts have no mutation. | TASK-25: HTTP route absence or `UNSUPPORTED_OPERATION`. |
| TEST-21 | Reuses TASK-09 caller-context tests: invalid context is denied before storage; application safe-error paths remain no-write. | TASK-25: trusted-header parsing and HTTP envelopes. |
| TEST-22 | Reuses TASK-09's complete role/operation/account-scope matrix at the application boundary. | TASK-25: complete public-route matrix. |
| TEST-23 | Every movement-bearing command refuses a foreign movement exactly like a missing movement, with no write; TASK-09 supplies path/body validation helpers. | TASK-25: path/body and cross-account cases through HTTP. |
| TEST-24 | Reuses identifier, fingerprint, money, timestamp, and command-validation tests; no invalid input has an effect. | TASK-25: transport/schema edge cases; TASK-26: safe log omission/tokenization and injection resistance. |
| TEST-25 | Reruns TASK-04's value-formatted-SQL static mutation suite and the existing runtime injection cases. | TASK-31: release-candidate rerun. |
| TEST-26 | The validator scans the repository, fixtures, source, expected application responses, and TASK-23 evidence for secret/card and prohibited-data patterns. | TASK-25: HTTP responses; TASK-26: runtime logs; TASK-34: final evidence bundle. |
| TEST-27 | Reuses TASK-02 evidence: the baseline required-secret set is empty and `.env.example` contains safe samples only. | The first task that introduces a required secret must add and pass missing-secret startup failure before completion. |
| TEST-28 | Forced unexpected write and read exceptions produce safe `INTERNAL_ERROR`, roll back/end snapshots, and expose no injected detail. | TASK-25: HTTP envelope; TASK-26: correlation and observability behavior. |
| TEST-29 | No TASK-23 passing claim because structured logging and bounded metrics do not exist. | TASK-26: complete implementation and proof. |
| TEST-30 | Reuses schema guard, immutable-table, application-interface, and direct-corruption readiness tests; unsupported application mutation methods remain absent. | TASK-25: HTTP readiness projection; TASK-31: release-candidate corruption rerun. |

Structured safe security evidence for rejected commands is an observability artifact owned by TASK-26 under DEC-0051; read-specific evidence remains traced to TASK-24/TEST-41. This is exact ownership, not skipped evidence.

## Acceptance evidence

- Focused tests: safe write/read fault injection; unsupported-operation and full substitution matrix; governance-validator mutations; TASK-19 through TASK-22 scheduled negative cases.
- Reused tests: `tests/security/test_caller_and_authorization.py`, `tests/security/test_sql_static_scan.py`, `tests/unit/test_identifiers.py`, `tests/integration/test_migrations.py`, `tests/integration/test_migration_protections.py`, `tests/integration/test_migration_runner_edges.py`, and `tests/integration/test_readiness.py`.
- Required broader gates: governance validator, Ruff check/format, mypy, complete pytest suite, CI checks, independent exact-head review, and no open Blocker or Major.
- Code PR and implementation evidence: PR #79; implementation commit `3072eecf4ca319160d8a0893ca0d632e8f90d8c4`, based on the Specs-pointer merge `010b40fbdae97befcd8e87090fe4c4ce94eb1e7d`.
- Local result before the documentation commit: governance PASS; Ruff and mypy PASS; 789 tests PASS on Python 3.12.14. Exact-head CI and independent review remain required before JDC approval.

## Non-claims

- TASK-23 does not close shared TEST identifiers at release level.
- No HTTP route/envelope, structured log, metric, runtime correlation, required secret, final evidence bundle, container, deployment, or production control is implemented here.
- No skipped, quarantined, flaky, or not-applicable classification is used for a required facet.

## Completion

- Review findings: the first fresh-context review found three Majors—unsafe unexpected read exceptions, incomplete movement-substitution coverage, and incomplete scheduled/evidence closure. All are addressed in implementation commit `3072eecf4ca319160d8a0893ca0d632e8f90d8c4`; exact-head re-review is pending.
- Residual risks: only the explicitly assigned TASK-25, TASK-26, TASK-31, and TASK-34 facets above remain. Any missing finalizer or incomplete release rerun fails the gate.
- Next safe action: run exact-head gates and independent review, present the exact SHA to JDC, and merge only after JDC approval without changes.
