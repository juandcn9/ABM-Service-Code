# TASK-26 Tester Report (second pass)

## Header

- Task: TASK-26 (structured logs, bounded metrics, safe health, TEST-39 and TEST-41 facets)
- Head reviewed: PR #100, branch `fix/task-26-tester-majors`, commit `de2ca701fadcb72f26d0cb5421fae91d55c6eca6`, tree `031da46cd8e4b06a8a90241ff9ae5ffac91d2e63`
- Specs pinned: v1.9.12, `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f` (tag `v1.9.12`)
- Date: 2026-10-11. Role: fresh-context Tester. Read-only review; nothing committed, pushed, or merged by the Tester.
- Prior pass: `docs/evidence/TASK-26-tester-report.md` (FAIL at `7ff1580`, Majors F1 to F6).

## Gate results (on `de2ca70`)

| Gate | Result |
|---|---|
| `pytest -p no:cacheprovider` | `951 passed, 1 warning in 145.11s` (exit 0; the warning is a Starlette httpx deprecation notice) |
| `ruff check .` | All checks passed (exit 0) |
| `ruff format --check .` | 147 files already formatted (exit 0) |
| `mypy src harness tests scripts` | Success: no issues found in 86 source files (exit 0) |
| `scripts/validate_governance.py` | exit 0 |
| `scripts/validate_toolchain.py` | exit 0 |

## Fix verification

| Finding | Verdict | Evidence |
|---|---|---|
| F1 UTC `ts` and `severity` on every line | PASS | `EventSink.emit` stamps both (`events.py`); caller-supplied `ts` is refused by the allowlist. Mutants: drop `ts` (FAIL), severity always INFO (FAIL). |
| F2 unexpected error not re-raised | PASS | `main.py` middleware catches `Exception` around `call_next` and returns the `INTERNAL_ERROR` envelope. Test uses `raise_server_exceptions=True`. Restoring the 7ff1580 `main.py` fails the test. In-process only; live uvicorn not run. |
| F3 read-only scan connection | PASS | `scan_aged_items.open_read_only()` is what `main()` calls; the refuses-writes test uses it. Read-write mutant fails. |
| F4 submitted and authorized card items | PASS | `PENDING_STATES` includes both; parametrized test covers each. Dropping either state fails one case. |
| F5 manifest image digest and test summary | PASS | `image_digest` equals the `toolchain.toml` pin; `test_summary` is required with `--manifest`. Empty-digest and not-required mutants fail. |
| F6 Code cites DEC-0061 to DEC-0064 at a pin | PASS (substance) | `git show 1f6a26d:governance/decisions.md` contains the four rows; `main` pins `v1.9.12` / `1f6a26d` (PR #101). The work item citation was stale; corrected on this branch (T2-3). |
| F7 response body asserted | PASS | Status, message, and `SELECT` absence asserted. Correlation and code were not asserted at the time (T2-2); addressed on this branch. |
| F8 rejected trace read | PASS | Rejected trace read: decision `rejected`, role recorded, no `account_token`. Mutant forcing `permitted` fails. |

## Scope checks

- No new public route: 24 app routes match the 24 operations in `contracts/openapi.yaml` at `1f6a26d` (DEC-0053).
- Log allowlist enforced before stamping; unknown fields raise.
- Bounded labels: `event`, `decision`, `caller_role` in bounded sets; `operation` is the route template; `result_code` is the closed error-code set and is not in `BOUNDED_LABELS` (Note).
- Tokenization: identifiers emitted as tokens; a forced 500 produced no raw identifiers.
- TEST-41: read events for account and trace reads, permitted and rejected, with no financial fields.
- TEST-39: scan connection is read-only; the aged query is a SELECT; the scan writes only stdout and the manifest.

## Mutants (scratch copy of `de2ca70`, targeted tests)

| # | Mutant | Result |
|---|---|---|
| M1 | remove `ts` stamp | FAIL (test caught it) |
| M2 | restore 7ff1580 `main.py` | FAIL (`RuntimeError` propagates) |
| M3 | `open_read_only` read-write | FAIL |
| M4 | drop `submitted` | FAIL (1 of 2 cases) |
| M5 | drop `authorized_with_hold` | FAIL (1 of 2 cases) |
| M6 | empty `image_digest` | FAIL |
| M7 | `test_summary` not required | FAIL |
| M8 | read decision always `permitted` | FAIL |
| M9 | severity always INFO | FAIL |
| M10 | exception text in message | FAIL |
| M11 | correlation id dropped from 500 envelope | SURVIVED (T2-2) |
| M12 | 500 severity not ERROR | SURVIVED (T2-1) |

## Findings

| ID | Class | Description | Status |
|---|---|---|---|
| T2-1 | Minor | No test asserts ERROR severity for a 500 (M12 survives). | Fixed on this branch: forced-error test asserts ERROR severity and status 500. |
| T2-2 | Minor | Forced-error test does not assert `error.code` or `meta.correlation_id` (M11 survives). | Fixed on this branch. |
| T2-3 | Minor | Work item cited the old pin `v1.9.11` / `d2211b53`. | Fixed on this branch. |
| T2-4 | Minor | Manifest test checked digest format only, and its summary fixture does not match the run's count. | Fixed on this branch: digest compared to `toolchain.toml`. |
| T2-5 | Minor | F10 still open: no SHA-format or HEAD check on `--spec-commit` and `--code-commit`. | Scheduled: Builder, trigger TASK-27. |
| T2-6 | Note | `container_digest()` returns `""` silently if the pin has no `@`. | `validate_toolchain.py` covers the pinned file; no code change. |
| T2-7 | Note | Without an events sink, internal errors produce no log line. Intended under F2. | Scheduled: Builder, trigger TASK-27. |
| F9, F12, F13 | Note | Carried from the first pass (fixed salt, percent-encoding, buffering). | Recorded limits, unchanged. |

## Verdict

**PASS** for TASK-26 at `de2ca70`. No Blocker or Major. F1 to F8 are fixed with tests that fail on mutation. Minors T2-1 to T2-4 are fixed on the fix branch after this report; T2-5 is scheduled.

## Not verified

- Live uvicorn run, so the F2 traceback in the server log was not observed directly.
- The aged scan CLI end-to-end on a real database file (covered only by in-process tests calling `main()`).
- Secret-pattern scan of the repository (TEST-26 evidence scan belongs to TASK-34).
- `ponytail-review` was not run.
