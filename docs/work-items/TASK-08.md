# Work item: TASK-08 — monetary value objects, results, fingerprints, clock port

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-08`; `INV-01`, `INV-08`, `INV-12`, `INV-17`; `TEST-15`, `TEST-24`, `TEST-36` (domain-side building blocks only)
- Decision, gap, or risk records: `DEC-0002`, `DEC-0011`; no new decision or gap; DV-01 and DV-02 in `docs/governance/deviations.md`
- Owner role: Builder (Claude Code); independently verified (see Independent verification)

## Scope

- Objective: provide the pure domain building blocks later TASKs share: integer-cent USD money, canonical opaque identifiers and UTC instants, typed application results with the stable error codes, a canonical idempotency fingerprint, and the controllable clock port with a deterministic test double.
- Included files/components: `src/abm/domain/{errors,money,identifiers,results,fingerprint}.py`; `src/abm/ports/clock.py`; `harness/clock.py`; unit tests; `mypy` in CI and docs now also covers `harness`.
- Explicit exclusions: any persistence, transaction, or idempotency storage (`TASK-07`, `TASK-10`); choosing which request fields belong in each operation's fingerprint (decided per operation in `TASK-10` and later against the Specs); authorization and caller context (`TASK-09`); a real system clock adapter (composition root, later); movement, hold, or ledger logic.
- Dependencies and entry gate: `TASK-03` Verified (Code `aa740bb`).

## Acceptance evidence

- Focused tests (`pytest tests/unit`): money accepts only integer cents (rejects float, bool, string, `None`, zero, negatives for amounts, values above 2^53-1) with exact range-checked arithmetic and USD only; identifiers accept exactly 1-128 URL-unreserved ASCII characters and reject reserved, whitespace, control, Unicode digits and letters, percent-encoded forms, trailing newline, oversized, injection strings and non-strings; instants parse only `YYYY-MM-DDTHH:MM:SSZ` and reject impossible dates, offsets, fractions, and trailing text; results carry only the 17 stable codes; the fingerprint is deterministic, key-order independent, changes with every input, keeps types, null, and absent distinct, resists delimiter collisions, rejects floats, bools, lists, and objects, and matches an independently computed SHA-256 vector; the clock never moves on read and only advances by whole non-negative seconds.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head, plus the same commands locally; the import-boundary tests confirm `domain` still imports only the standard library.
- Failure, concurrency, authorization, and recovery cases: not applicable at this layer.
- Documentation/trace updates: README, CHANGELOG, this work item.

## Implementation notes

- Reversible technical choices: value objects validate in the constructor and raise `InvalidValue`; the application layer turns that into `VALIDATION_ERROR`. Exact `type(...) is int` checks reject `bool` and subclasses. `Money` is signed (balances) with `Money.positive` for requested amounts. The error-code set is the stable list in `specs/04-api.md` section 2; adding a code needs a Specs change. Results use Python 3.12 generics.
- `format_instant` floors sub-second precision to match the stored second-resolution form; it never rounds up, so a hold or a seven-year deadline is never evaluated in the future.
- The fingerprint includes the operation name and a caller-chosen field map but not the idempotency key (the key is the lookup scope). Whether `instruction_id` belongs in a given operation's fingerprint is a per-operation decision for `TASK-10`; this task does not make it.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI runs the pinned 3.12.15.

## Completion

- Code commit/PR: PR #9, merged as `9fb729a`.
- Commands/checks and results: locally `pytest` 30 passed in this branch, `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, and both validators pass; CI results are on the PR.
- Review findings/resolution: Builder Audit `ponytail-review` (installed plugin 5.1.0, `full`, DV-01) found nothing to fix. Independent fresh-context review of head `d7e9140`: PASS with findings (zero Blocker/Major), plus a conflict with `main` in README/CHANGELOG. Resolved: the branch merged `main`; m1 (the money bound was not pinned to the schema literal) now has a literal test; m2 (`Error` did not enforce the OpenAPI message and retryable contract) now validates 1-256 printable ASCII characters and a real boolean; m3 (`Money` arithmetic with a non-Money operand raised `AttributeError`) now returns `NotImplemented` so it is a `TypeError`; M2 (`strftime('%Y')` is not zero-padded for years below 1000 on glibc, which would break the fixed 20-character stored form on Linux CI) is fixed by explicit formatting with tests for years 1, 999 and 9999. Observations carried forward: the fingerprint treats an absent and a null field as different, so `TASK-10`+ must normalize optional fields and add per-operation field-change tests; Python timestamp parsing is stricter than the schema CHECK (it rejects year 0000 and hour 24), which is the safe direction. Independently verified (see Independent verification).
- Residual risks: the fingerprint's field set per operation is not yet defined; an operation that omits a field that changes its effect would replay wrongly, so each `TASK-10`+ operation needs a test that every effect-relevant field changes the fingerprint.
- Next safe action: `TASK-10` (idempotency and registration) once `TASK-06` and `TASK-07` are merged; it must add the per-operation fingerprint field-change tests.

## Independent verification

- Role and context: Tester, fresh-context agents that did not build `TASK-08`, 2026-10-09. The sanitized report is committed at [`docs/evidence/TASK-08-tester-report.md`](../evidence/TASK-08-tester-report.md).
- Revision tested: Code PR #9 head `0a7e2af3e96c63abe667770885e09ee5c53ec1b9` (merged as `9fb729a`). Specs `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Result: PASS on re-verification of the fix head; the first review's findings (m1, m2, m3, M2, conflict with `main`) are resolved; zero Blocker, zero Major.
- Scope of "Verified": the domain value objects, typed results, fingerprint encoding, and clock port. `TEST-15`, `TEST-24`, and `TEST-36` are covered only on the domain side; the per-operation fingerprint field sets, the absent-versus-null rule, and field-change tests belong to `TASK-10` onward.
- Not verified: behavior on glibc locally (CI on Linux is the guard for the year-padding fix); Python 3.12.15 locally.
