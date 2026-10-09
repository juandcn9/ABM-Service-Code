# TASK-09 independent Tester report (sanitized record)

**Provenance:** final reports of two fresh-context reviewer/Tester agents on 2026-10-09 (first review of PR #10 head `977272c`, then a re-verification of the fix head `4161710`), launched by the Claude Code session that built `TASK-09`. The Builder reformatted them. Evidence input, not Specs authority.

- Revision verified: Code PR #10 fix head `4161710816189ab271c867199155dea7a3103010`. The merged head `4598e060ca7eb1ac803b677aecd442e4f1279ff8` (merge commit `e3aada8`) has an identical tree (`main` merged in; checked with `git diff --quiet`).
- Specs: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Environment: Python 3.12.10 on Windows (throwaway virtual environments from `requirements-dev.lock`, hash-verified). CI evidence on Linux with CPython 3.12.15.

## Result

PASS (re-verification of the fix head). The first review was: implementation correct, no Blocker, two Major test-evidence gaps, now closed.

## Checks (re-verification at `4161710`)

| Check | Result | Evidence summary |
|---|---|---|
| Authorization matrix against `specs/06` section 4 and every OpenAPI `x-authorized-role` | PASS | Parsed programmatically: 22 operations plus the non-public legal-hold port match; health operations are unauthenticated and not authorization operations. |
| Independent literal in the tests | PASS | `SPEC_MATRIX` is hand-written from the Specs and compared with each role's operations. |
| Mutation tests (265 mutants on `authorization.py`) | PASS | 234 killed; the 31 survivors are all no-ops ("move X into the role that already holds it"); no non-equivalent survivor. The F1 case (moving `API-12` to `card_orchestrator`) and the F2 case (unscoping `API-03`) now fail tests. |
| Hostile inputs for `strict_json` and `parse_caller_context` | PASS | Non-text input, `1e999`, `-1e999`, `1E+99999999999`, lone surrogates (escaped and raw), nesting up to 1 000 000 levels, over-long integers, BOM, duplicate keys, trailing text, NaN: every failure is `InvalidValue` (or `UNAUTHORIZED` for headers); valid documents decode unchanged. |
| Boundaries | PASS | `api` imports only `application` and `domain`; `application` only `domain` and `ports`; no FastAPI import. |
| Tests | PASS | Deterministic; `pytest -W error` gives 55 passed three times in a row. |
| Local gates and CI | PASS | `ruff`, `mypy`, both validators clean; `validate-governance` and `quality-gates` green on both heads, 55 tests on CPython 3.12.15. |

## Findings

- Resolved from the first review: F1 (the matrix test did not assert which role holds which operation), F2 (history-read cross-account denial untested and the scoped set taken from the implementation), F3 (stale test counts), F4 (non-text input to `strict_json` and non-mapping headers raised `AttributeError`), F5 (`1e999` and lone surrogates accepted).
- Observation O1: a `Mapping` subclass that raises on iteration propagates its exception from `parse_caller_context`; the contract is a normalized mapping from the trusted adapter (`TASK-25`).
- Observation O2: `0e999999` and `1e-400` become `0.0` (finite, by design; money never takes floats).
- Carried to `TASK-25` and `TASK-23`: the adapter must pass one normalized string-keyed header mapping, limit body size, and route every body through `strict_json`; the 401 versus 403 treatment of an unknown role (a 403 here) and the meaning of "contradictory" context (implemented as duplicate or multi-valued headers) are interpretations recorded in the work item; if the Specs intend more, that is a GAP.

## Scope and qualifiers

Parsing, authorization, and transport-validation halves of `TEST-21` to `TEST-24` only; HTTP wiring, the deployment-mode trust check, and cross-account movement substitution remain for later tasks. `RISK-0002` (trusted ingress) is unchanged.
