# Work item: TASK-25 — HTTP binding with exact envelopes

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.10` / `58d040fdc56450bb61270ee3ce106eb73ab71245` (DEC-0055 for the connection model and the demonstration boundary).
- TASK and affected IDs: `TASK-25`; `DEC-0051`; `API-01` to `API-24`; `SEC-01` to `SEC-04`, `SEC-08`, `SEC-10`; HTTP facets of `TEST-20` to `TEST-24`, `TEST-26`, `TEST-28`, `TEST-30`; `TEST-46`.
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.

## Implemented (merged)

- Slice 1, PR #89, merged as `8faf02e` at approved head `5557f86`: envelopes, stable error-code to HTTP status map, trusted-context denial, registration and account read.
- Slice 2, PR #91, merged as `ddfcbe5` at approved head `2375802`: the remaining 20 operations bound to their routes.
- Slice 3, PR #92, merged as `1ae2a15` at approved head `4d29109`: health routes `API-20` and `API-21`, and the HTTP forms of `TEST-20`, `TEST-22`, `TEST-23`, `TEST-24`, `TEST-26`, `TEST-30`.
- Slice 4, this PR: conformance tooling for `TEST-46` (standard library only, DEC-0055 demonstration scope, option (b) of the decision record): `scripts/schema_lite.py` (a JSON Schema checker for the keywords the contract uses; refuses any keyword it does not support), `scripts/check_http_conformance.py` (probes all 24 paths and checks each response against the contract's declared statuses and schemas), and `tests/unit/test_schema_lite.py`.

## Remaining before TASK-25 can be Implemented

- `TEST-46`: success probes for the 19 operations that the conformance driver does not yet send a successful request to. Each needs a valid success body and a checked success schema. The driver currently checks the 401, 403, malformed-body 400 and (for the account read) 404 responses of every path, and the success bodies of registration, account read, history, trace and both health routes.
- The conformance driver runs as a script, not inside the test suite, so `TEST-46` is evidence-based rather than automated in CI (option (b)).

## Non-claims

- `TEST-29` (structured logs, bounded metrics, redaction) belongs to `TASK-26` under DEC-0051.
- The evidence bundle facet of `TEST-26` belongs to `TASK-34`.
- The lock serializes requests in one process. No concurrency or throughput claim (DEC-0055).

## Scheduled items

- Success probes for the remaining operations (`TEST-46`): owner Builder; trigger: before TASK-25 is Implemented.
- Structured-log facet (`TEST-29`): owner Builder; trigger: `TASK-26`.
- Production readiness wiring (no entry point wires a real check yet): owner Builder; trigger: `TASK-26` or `TASK-27`.
