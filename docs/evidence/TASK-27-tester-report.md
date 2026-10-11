# TASK-27 Tester report (merged revision)

**Task:** TASK-27 non-root read-only container. **Merged commit:** 772ee1f (PR #104). **PR head:** 0ed7c79. **Specs pin:** v1.9.12 / 1f6a26d. **Date:** 2026-10-11. **Role:** fresh-context Tester, read-only (no tracked files changed).

## Gates on 772ee1f

| Gate | Result |
|---|---|
| pytest | `987 passed, 1 warning in 145.34s` (exit 0) |
| ruff check . | passed (exit 0) |
| ruff format --check . | 155 files already formatted (exit 0) |
| mypy src harness tests scripts | exit 0 (90 files, no issues) |
| validate_governance.py | PASSED (exit 0) |
| validate_toolchain.py | PASSED (exit 0) |

## Scope

| Item | Evidence | Result |
|---|---|---|
| 1 Config | src/abm/config.py; tests/unit/test_config.py | Pass |
| 2 Readiness | src/abm/main.py (app_from_environment, UnavailableUnitOfWork); tests/integration/test_container_entry.py | Pass. SERVICE_UNREADY for reads untested |
| 3 Dockerfile | Digest equals toolchain.toml; hash-verified install at build; UID 10001; VOLUME /data; --no-access-log; --workers 1 | Pass by reading; no test asserts it |
| 4 check_container | scripts/check_container.py (container_failures, ReadonlyRootfs); tests/unit/test_check_container.py | Pass |
| 5 CI | Run 38158933406 on head 0ed7c79: container-check, validate-governance, quality-gates success; http-conformance failure. Workflow diff is additions only | Pass |
| 6 Secrets | .dockerignore excludes CLAUDE.md, .env, docs, tests, scripts; Dockerfile copies only requirements.lock, src, migrations | Pass by reading |

## Mutants

| Mutant | Test | Result |
|---|---|---|
| (a) clock allows controlled | tests/unit/test_config.py | killed |
| (b) container_failures ignores readonly | tests/unit/test_check_container.py | killed |
| (c) drop --no-access-log | no Dockerfile test exists | uncovered |
| (d) fallback hard-coded DATABASE_UNAVAILABLE | tests/integration/test_container_entry.py | uncovered |

## Open decisions (not defects)

1. Scope item 7 reduced to in-process conformance (JDC decision pending).
2. `http-conformance` fails: the CI token cannot read the private Specs repository (access decision pending). It also fails on the merge-commit push run 38159697564; the other jobs passed there.

## Findings

| ID | Class | Status |
|---|---|---|
| F1 | Minor | Open: no automated assertion for --no-access-log, --workers 1, or UID 10001 (mutant c) |
| F2 | Minor | Open, disclosed: real startup reason codes other than DATABASE_UNAVAILABLE are untested (mutant d) |
| F3 | Note | SERVICE_UNREADY for reads untested; only writes are |
| F4 | Note | ABM_CLOCK_MODE refuses controlled in every mode, stricter than Specs section 2 (disclosed) |
| F5 | Note | --no-access-log and --workers 1 live only in ENTRYPOINT; a CMD override could drop them |

## Tree and head checks

`git diff --stat 0ed7c79 772ee1f` is empty: the merge tree equals the PR head tree. Run 38158933406 is on head 0ed7c79.

## Verdict: PASS

No Blocker or Major. Open decisions remain with JDC.

## Not verified

The container image was built and run only in CI (run 38158933406), not on this host. TEST-33 evidence is CI-only.
