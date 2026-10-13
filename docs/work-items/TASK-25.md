# Work item: TASK-25 — HTTP binding with exact envelopes

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.9.10` / `58d040fdc56450bb61270ee3ce106eb73ab71245` (DEC-0055 for the connection model and the demonstration boundary).
- TASK and affected IDs: `TASK-25`; `DEC-0051`; `API-01` to `API-24`; `SEC-01` to `SEC-04`, `SEC-08`, `SEC-10`; HTTP facets of `TEST-20` to `TEST-24`, `TEST-26`, `TEST-28`, `TEST-30`; `TEST-46`.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.

## Implemented (merged)

- Slice 1, PR #89, merged as `8faf02e` at approved head `5557f86`: envelopes, stable error-code to HTTP status map, trusted-context denial, registration and account read.
- Slice 2, PR #91, merged as `ddfcbe5` at approved head `2375802`: the remaining 20 operations bound to their routes.
- Slice 3, PR #92, merged as `1ae2a15` at approved head `4d29109`: health routes `API-20` and `API-21`, and the HTTP forms of `TEST-20`, `TEST-22`, `TEST-23`, `TEST-24`, `TEST-26`, `TEST-30`.
- Slice 4, this PR: conformance tooling for `TEST-46` (standard library only; script-run evidence, DEC-0056): `scripts/schema_lite.py` (a JSON Schema checker for the keywords the contract uses; refuses any keyword it does not support), `scripts/check_http_conformance.py` (probes all 24 paths and the success flows of all 22 v1 operations, and checks each response against the contract's declared statuses and schemas; 92 responses conform), and `tests/unit/test_schema_lite.py`.

## Verification

- Verified by the independent Tester pass on the fix head `e5b550f` (PR #95, merged as `2c439fd`, tree identical), accepted for the merged content by DEC-0059. Report: `docs/evidence/TASK-25-tester-report.md`.

## Tester FAIL on `a81b3c6` and fix

- Tester (fresh context) found two Majors: an oversized integer query returned 500 instead of 400 (fixed: `_int_query` passes such values to the application, which refuses them with VALIDATION_ERROR); the transfer strict-body parse had no HTTP test (fixed: duplicate-key and malformed bodies are refused before any money moves). The integer fix has a test that fails on the old code. The transfer tests are new coverage for a route whose code did not change; they pass on the old code and guard against a future regression.
- Minors recorded as limits (see Non-claims).

## Acceptance evidence for TEST-46

- Success flows cover all 22 v1 operations: registration, account read, history, trace, and the 18 operations of slice 2 (incoming and outgoing ACH, transfer, card lifecycle, correction, restriction, closure), each through a real business sequence.
- Every probe response is checked against its declared status and schema; any refused success step is a deviation.
- The script is run as evidence (DEC-0056). Automated CI execution is a TASK-27 item.

## Non-claims

- `TEST-29` (structured logs, bounded metrics, redaction) belongs to `TASK-26` under DEC-0051.
- The evidence bundle facet of `TEST-26` belongs to `TASK-34`.
- The lock serializes requests in one process. No concurrency or throughput claim (DEC-0055).
- Framework responses for unknown routes (404) and wrong methods (405) are `{"detail": ...}`, not the envelope. The contract does not declare them (Tester Minor 3 on `a81b3c6`, recorded as a limit).
- The conformance script's role probe asserts 403 FORBIDDEN_SCOPE for every role outside each operation's matrix row (Tester Minor 4, closed on `fix/minors-c`).
- Unknown-account 404 is probed for every account-scoped operation that declares 404, with the success-flow body of each (Tester M2 on head 6018166, closed on `fix/minors-c`).

## Scheduled items

- Structured-log facet (`TEST-29`): owner Builder; trigger: `TASK-26`.
- Production readiness wiring (no entry point wires a real check yet): owner Builder; trigger: `TASK-26` or `TASK-27`.
