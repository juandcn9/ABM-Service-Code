# TASK-26 Tester Report (third pass, merged revision)

## Header

- Task: TASK-26 (structured logs, bounded metrics, safe health, TEST-39 and TEST-41 facets)
- Merged commit tested: `d45e766` (merge of PR #100). Merge tree: `9a386179e4f6703cd32b86d24d25e7dbe5637fd8`
- Previous tested head: `de2ca70`, tree `031da46cd8e4b06a8a90241ff9ae5ffac91d2e63` (second pass, `TASK-26-tester-report-2.md`)
- Specs pin: v1.9.12 / `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f`
- Note: `origin/main` has since advanced to `fc4a891` (PR #99, docs only). Not part of the tested revision.
- Date: 2026-10-11. Role: fresh-context Tester (read-only; the Tester committed nothing).

## Gate results (`d45e766`)

| Gate | Result |
|---|---|
| `pytest -p no:cacheprovider` | `951 passed, 1 warning` (exit 0) |
| `ruff check .` | All checks passed (exit 0) |
| `ruff format --check .` | 148 files already formatted (exit 0) |
| `mypy src harness tests scripts` | exit 0, 86 files |
| `scripts/validate_governance.py` | exit 0; Specs pointer v1.9.12 / 1f6a26d |
| `scripts/validate_toolchain.py` | exit 0 |

## Diff scope (`de2ca70..d45e766`, 9 files)

- Code tests: `tests/integration/test_observability.py`
- Docs: `docs/work-items/TASK-26.md`, `docs/evidence/TASK-26-tester-report-2.md`
- Pointer (DEC-0037, PR #101, reviewed clean): `README.md`, `SPEC_VERSION`, `docs/governance/repository-policy.md`, `docs/work-items/TASK-01.md`, `scripts/validate_governance.py`, `tests/security/test_governance_validator.py`
- `src/` and `migrations/`: no change.

The pointer files differ from `7ff1580` only in the version string (`v1.9.11` to `v1.9.12`) and the commit (`d2211b53...` to `1f6a26d3...`), including print text. Pass.

## Scope checks

| Item | Evidence | Result |
|---|---|---|
| UTC `ts` and `severity` on every event | `events.py` `_severity`; the sink stamps both; `test_each_request_emits_one_line_with_allowed_fields_only` | PASS |
| Unexpected error not re-raised | `main.py` middleware catches around `call_next`; `test_an_unhandled_error_is_not_re_raised_to_the_server` (`raise_server_exceptions=True`) | PASS |
| Scan connection read-only | `scan_aged_items.py` `open_read_only` (`mode=ro`), used by `main()`; `test_the_scan_refuses_writes_through_its_read_only_connection` | PASS |
| Submitted and authorized card items scanned | `aged.py` `PENDING_STATES`; `test_the_scan_finds_submitted_outgoing_and_authorized_card_items` | PASS |
| Manifest `image_digest` and required `test_summary` | `scan_aged_items.py` `container_digest()`; `test_the_manifest_records_exact_revisions_migrations_and_the_scan_result`; `test_a_manifest_without_a_test_summary_is_refused` | PASS |
| Forced-error assertions | error code, correlation id, status 500, ERROR severity in `test_an_unhandled_error_is_not_re_raised_to_the_server` | PASS |
| No new public route | 24 app routes equal the 24 operations in `contracts/openapi.yaml` at `1f6a26d` (DEC-0053) | PASS |

## Mutants (one mutation each, scratch copy of `d45e766`)

| # | Mutation | Test | Result |
|---|---|---|---|
| 1 | 500 severity forced to INFO | forced-error test | killed |
| 2 | `image_digest` forced empty | manifest test | killed |
| 3 | `mode=ro` changed to `mode=rw` | refuses-writes test | killed (write did not raise) |
| 4 | pre-fix `main.py` (exception re-raise) | forced-error test | killed (`RuntimeError` re-raised) |

## Findings

| ID | Class | Description | Status |
|---|---|---|---|
| F-1 | Note | The brief's tree `79950a9` belongs to PR #100's head `7881d48`. The tested merge tree is `9a386179`. The difference is the DEC-0037 pointer change, which reached `main` before PR #100 merged. | Explained above |
| F-2 | Minor | The manifest test fixture passes `test_summary` as "945 passed, 1 warning" while the run reports 951. The value is an input fixture, not a claim checked against the run. | Recorded; no code claim depends on it |

No Blocker or Major.

## Verdict

**PASS** for TASK-26 at merged revision `d45e766`. No Blocker or Major. All fixes from the first pass (F1 to F8) are verified with tests that fail on mutation. The second-pass Minors T2-1 to T2-4 are fixed; T2-5 to T2-7 are scheduled or noted in the work item.

## Not verified

- Contents of `fc4a891` (PR #99): docs only; not diffed by this pass.
- Live uvicorn run (the F2 traceback in the server log was not observed directly).
- The container image digest was checked for equality with `toolchain.toml` only; the image was not pulled.
- Coverage was not measured. The run was Windows-only.
- Mutants 1 to 3 were applied by a text-mode rewrite that normalized CRLF to LF; each failed its named test.
