# TASK-08 independent Tester report (sanitized record)

**Provenance:** final reports of two fresh-context reviewer/Tester agents on 2026-10-09 (first review of PR #9 head `d7e9140`, then a re-verification of the fix head `0a7e2af`), launched by the Claude Code session that built `TASK-08`. The Builder reformatted them. Evidence input, not Specs authority.

- Revision verified: Code PR #9 head `0a7e2af3e96c63abe667770885e09ee5c53ec1b9` (merged as `9fb729a`, a merge commit that adds nothing else).
- Specs: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Environment: Python 3.12.10 on Windows (throwaway virtual environments from `requirements-dev.lock`, hash-verified). CI evidence on Linux with CPython 3.12.15.

## Result

PASS (re-verification of the fix head). The first review at `d7e9140` was PASS with findings; all are resolved.

## Checks (re-verification at `0a7e2af`)

| Check | Result | Evidence summary |
|---|---|---|
| Merge state and CI | PASS | CLEAN; `validate-governance` and `quality-gates` green on the push and pull-request runs; 30 tests passed on CPython 3.12.15. |
| Money bound pinned to the schema literal | PASS | `MAX_CENTS == 9007199254740991`; mutating it to `2**53` fails a test. Boundary values agree with the SQLite CHECK ranges (10 cases). |
| `Error` contract | PASS | Message must match the OpenAPI `^[\x20-\x7E]+$` with length 1 to 256 and `retryable` must be a real boolean; hostile inputs (non-str types, bool lookalikes, `\x7f`, `\x1f`, newlines, very long text) all raise `InvalidValue`. |
| `Money` with non-Money operands | PASS | `Decimal`, `float`, `str`, `None`, int subclasses, lists, and objects give `TypeError`; subclasses of `Money` still work. |
| `format_instant` | PASS | Explicit formatting replaces `strftime('%Y')` (not zero-padded for years below 1000 on glibc); 28 instants, including years 1, 99, 999, 1000, 9999 and leap days, equal SQLite's own output, are 20 characters, and round-trip. No other locale-dependent formatting call remains. |
| Identifiers and instants against SQLite and OpenAPI | PASS | 20 020 identifier cases and 550 timestamp boundary cases: no mismatches; Python is stricter only in the safe direction (rejects year 0000 and hour 24). |
| Fingerprint | PASS | Independent recomputation equals the code; byte-identical under three hash seeds; no collisions across type, null, delimiter, and key/value groups. |
| New defects from the fixes | None | Every `Error` and `failure` construction in `src`, `harness`, `scripts`, and tests was checked. |
| Mutation tests | PASS | Reverting each fix individually fails a test, except the `strftime` revert, which only fails on glibc (Linux CI is the guard). |

## Findings

- Resolved from the first review: m1 (constant not pinned), m2 (`Error` contract), m3 (non-Money arithmetic), M2 (year padding on Linux), the conflict with `main`.
- Observation O1: the year-padding regression test cannot detect its own revert on Windows (CI on Linux is the guard).
- Observation O2: the `Error` test does not list `\x7f` and `\x1f` directly (confirmed manually that they are rejected).
- Observation O3: the fingerprint treats an absent and a null field as different; each later operation must normalize optional fields and test that every effect-relevant field changes its fingerprint.

## Scope and qualifiers

`TEST-15`, `TEST-24`, and `TEST-36` are covered only on the domain side (building blocks); the per-operation fingerprint field sets, the absent-versus-null rule, and the field-change tests belong to `TASK-10` onward. Local evidence is Windows 3.12.10; Linux evidence comes from CI only.
