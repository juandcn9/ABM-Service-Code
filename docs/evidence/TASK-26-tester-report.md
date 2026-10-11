# TASK-26 Tester Report

## Header

- Task: TASK-26 (structured logs, bounded labels, read evidence, aged scan, manifest)
- Code head: `7ff1580f19bc6a97a01967a4534daae80b0eac26` (merge of PR #98); tree `848d3228f08f529dcc25e4629c18f0773729565d`
- Specs pinned version: v1.9.11, commit `d2211b53a0570437b7fa9ddb1a1ba46969d6ac40` (read via `git show d2211b5:<path>`)
- Tester role: fresh-context Tester
- Date: 2026-10-11

## Gate results

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q` | `945 passed, 1 warning in 143.75s` (exit 0; warning is a Starlette httpx deprecation) |
| `python -m ruff check .` | `All checks passed!` (exit 0) |
| `python -m ruff format --check .` | `148 files already formatted` (exit 0) |
| `python -m mypy src harness tests scripts` | `Success: no issues found in 86 source files`; exit 0 |
| `python scripts/validate_governance.py` | `TASK-01 VALIDATION PASSED`, exit 0 |
| `python scripts/validate_toolchain.py` | `TASK-02 VALIDATION PASSED`, exit 0 |

## Scope checks

- (a) Structured logs: PARTIAL. Allowlisted fields are enforced (`events.py:65`); one JSON line per event; no request bodies. FAIL on UTC timestamps and severity: `EventSink.emit` writes neither. See F1.
- (b) Bounded labels: PASS. `event`, `decision`, `caller_role` refused outside their sets; unknown roles map to `none`; no account, movement, or caller id is a label.
- (c) Tokenization: PASS for emitted fields (`account_token`, `caller_token`, `item_token`, `correlation_id`). See F9 for reversibility.
- (d) TEST-41: PASS for permitted and rejected account reads. Permitted trace read tested; rejected trace read not tested (F8). Read events carry no financial fields.
- (e) TEST-39 scan: PASS on threshold validation and no state change. PARTIAL on read-only: `scripts/scan_aged_items.py:97` opens `mode=ro`, but no test exercises that line (F3).
- (f) TEST-28: PARTIAL. Handler returns constant message with correlation; log has status 500 and `INTERNAL_ERROR` with no exception text. Response body not asserted (F7). Starlette re-raises after the handler, so the traceback reaches the server log (F2).
- (g) Manifest: PARTIAL. Present: generated_at, spec_version, spec_commit, code_commit, migrations, aged_scan. Missing vs TEST-35: image digest and test summary (F5).
- (h) No new public route: PASS. 24 operations in the app match the 24 in `contracts/openapi.yaml` at the pinned commit.

## Mutant results

Each mutant applied to a scratch copy of `7ff1580`; run with `tests/integration/test_observability.py` (base: 26 passed).

| Mutant | Change | Result |
|---|---|---|
| M1 allowlist disabled | `events.py`: `unknown = set()` | KILLED |
| M2 raw account id logged | `main.py`: raw path segment as `account_token` | KILLED |
| M3 scan not read-only | `scan_aged_items.py`: plain `sqlite3.connect` | SURVIVED (F3) |
| M4 raw correlation logged | `main.py`: correlation untokenized | KILLED |
| M5 threshold optional | `scan_aged_items.py`: `default=24.0` | KILLED |
| M6 unexpected error unobserved | `main.py`: removed `_observe` in handler | KILLED |
| M7 card/outgoing pending state dropped | `aged.py`: `authorized_with_hold` replaced | SURVIVED (F4) |
| M8 exception text in response | `main.py`: `{exc}` in INTERNAL_ERROR message | SURVIVED (F7) |

## Findings

| ID | Class | File:line | Description | Status |
|---|---|---|---|---|
| F1 | Major | `src/abm/observability/events.py:65` | Events have no UTC timestamp and no severity field; specs/06 section 8 requires both. | Open |
| F2 | Major | `src/abm/main.py:180-186` | Starlette `ServerErrorMiddleware` re-raises after the app handler; uvicorn logs the traceback, which can contain SQL or amount text. Source-based; not reproduced against live uvicorn. | Open |
| F3 | Major | `scripts/scan_aged_items.py:97` | Read-only property of the shipped entry point is untested; a read-write connection passes all tests (M3). | Open |
| F4 | Major | `src/abm/persistence/aged.py` PENDING_STATES; `tests/integration/test_observability.py:198` | Only incoming ACH `pending` tested; card `authorized_with_hold` and outgoing `submitted`/`accepted_with_hold` untested (M7 passes). | Open |
| F5 | Major (JDC scope confirmation needed) | `scripts/scan_aged_items.py` build_manifest | TEST-35 requires image digest and test summary; neither present. DEC-0064 lists only revisions and scan results. | Open |
| F6 | Major | `docs/work-items/TASK-26.md` Authority | Cites DEC-0061 to DEC-0064, which are absent at the pinned commit d2211b5; they exist only on Specs main `a30f8fd`. Fix: bump the pin to a Specs release containing them, or record a waiver. | Open |
| F7 | Minor | `tests/integration/test_observability.py:290-312` | Unexpected-error test does not assert the response body (M8 survives). Current code correct. | Open |
| F8 | Minor | `tests/integration/test_observability.py:150` | No test for a rejected trace read (TEST-41 names trace reads). | Open |
| F9 | Minor | `src/abm/observability/events.py` `_TOKEN_SALT` | Fixed public salt; tokens of guessable ids are dictionary-reversible by anyone with logs and the repo. 64-bit truncation. Recorded as a shortcut in the work item. | Recorded limit |
| F10 | Minor | `scripts/scan_aged_items.py` main() | `--spec-commit` and `--code-commit` have no SHA format check and no check against git HEAD. | Open |
| F11 | Note | `scripts/scan_aged_items.py` main() | Entry point uses the system clock; `run_scan` takes `now` and is what tests use. | Note |
| F12 | Note | `src/abm/main.py` `_observe` | `account_token` from the raw URL segment; percent-encoded forms give a different token. Attribution only. | Note |
| F13 | Note | `src/abm/main.py` observe middleware | Response bodies buffered; recorded limit. | Note (recorded limit) |

## Verdict

**FAIL** for TASK-26 at head `7ff1580`. Rule: any Blocker or Major means FAIL. Majors: F1, F2, F3, F4, F5 (pending JDC scope confirmation), F6.

## Not verified

- Live uvicorn run to observe the traceback in the server log (F2 is from Starlette source, not reproduced).
- Runtime read-only behavior of the script on a WAL-mode database.
- Image digest and test summary in the manifest (not produced by this code; checked against spec text).
- Concurrency and throughput of the event stream (out of scope per the work item).
- No tracked file was edited, no branch was switched, and nothing was pushed or committed by the Tester.
