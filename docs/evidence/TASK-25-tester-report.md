# TASK-25 Tester report

Fresh-context Tester passes for TASK-25 (HTTP binding with exact envelopes). Recorded under DEC-0057 (disposition of the first FAIL) and DEC-0059 (acceptance of the fix-head pass for the merged content).

## Passes

| Pass | Revision | Verdict | Notes |
| --- | --- | --- | --- |
| 1 | `a81b3c6` (merged PR #93, tree equal to `94f2fec`) | FAIL | Majors: oversized integer query values returned 500 instead of 400; the transfer strict body parse had no HTTP test. Minors: framework 404 and 405 bodies are not the envelope; the conformance role probe does not assert 403. |
| 2 | `7898d30` (PR #95 fix) | FAIL | The duplicate-key transfer test used an incomplete body, so it would pass without the strict parser. |
| 3 | `e5b550f` (PR #95, merged as `2c439fd`) | PASS | No Blocker, Major or Minor findings. |

## Evidence for pass 3 (`e5b550f`)

- Full suite: 919 passed, 1 warning.
- `ruff check .`: all checks passed. `ruff format --check .`: 141 files formatted. `mypy src harness tests scripts`: no issues in 82 source files.
- Conformance: `scripts/check_http_conformance.py` against the v1.9.10 contract: "probed 92 responses across 24 paths", PASS.
- Mutant: transfer `strict_json` replaced by plain `json.loads`. Two cases fail (duplicate key and malformed body), so both are guarded.
- Mutant: `_int_query` reverted to plain `int()`. Two oversized-integer cases fail.

## Limits recorded (not findings)

- Unknown routes and wrong methods return framework bodies (`{"detail": ...}`), not the envelope. The contract does not declare them.
- The conformance script's role probe checks that the status is declared; the 403 role matrix is asserted by pytest.
- The unknown-account 404 is probed only for `GET /v1/accounts/{account_id}`.

## Not checked

- CI status on PR #95 was not part of the Tester pass.
- The Ponytail review was not part of the Tester pass.
