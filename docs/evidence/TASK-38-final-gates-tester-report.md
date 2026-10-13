# TASK-38 Tester report (independent reproduction of the final gates)

**Task:** TASK-38 local handover (DEC-0086). **Revision tested:** `d11db540e3ef5ca057249bd98a18ba729cfa65b8` (`main` after PR #158). **Gated by the author:** `9f1d74e739712842b4d05b1d0da8236ea012e3fb` ([`TASK-38-final-gates.md`](TASK-38-final-gates.md)). **Specs:** `v1.9.18` / `507719611c79425fdcfd63d0f5897aed66655db7`. **Date:** 2026-10-13. **Role:** fresh-context Claude Code subagent, read-only on the project, working in a fresh clone. It is a separate context from the author but the same model family, not a human tester. Scope: `docs/work-items/TASK-38.md`, section "Tester scope"; substitute evidence under deviation DV-05 (GitHub Actions is billing-blocked; JDC accepted the risk).

**Gate verdict: PASS.** **Documentation verdict: PASS with Minor findings.** No Blocker or Major finding.

## Environment

| Item | Value |
|---|---|
| Windows | 11 Home 10.0.26300, Git Bash |
| Python | 3.12.10 (repository pin 3.12.15; no Windows binary exists, DV-02) |
| Docker | engine and client 29.8.2 (Docker Desktop app version not read by the Tester; 4.95.0 per the author's read) |
| Fresh clone | `--no-hardlinks`, detached at `d11db54`, tree clean before and after |
| Contract | Specs `507719611c79425fdcfd63d0f5897aed66655db7`, sha256 `5e2118b182ca73e1fe3c645d6d726ac1ee48b6c45499b4fdc31c8f87b9c03b36` (matches the author's) |

The commands match `.github/workflows/governance-ci.yml`. The Tester added `-p no:cacheprovider` to pytest.

## Difference from the gated commit

`git diff --stat 9f1d74e d11db54`: two files, 37 insertions (`CHANGELOG.md`, `docs/evidence/TASK-38-final-gates.md`). Nothing under `src/`, `scripts/`, `tests/`, `Dockerfile`, `migrations/` or `.github/` changed.

## Gates

| Gate | Result | Summary line |
|---|---|---|
| `validate_governance.py` | PASS | TASK-01 VALIDATION PASSED |
| `validate_toolchain.py` | PASS | exact direct pins, SHA-256 locks, container digest, and safe example: passed |
| `ruff check .` | PASS | All checks passed! |
| `ruff format --check .` | PASS | 196 files already formatted |
| `mypy src harness tests scripts` | PASS | no issues found in 102 source files |
| `pytest -q -p no:cacheprovider` | PASS | 1325 passed, 1 warning in 388.63 s |
| `check_http_conformance.py` | PASS | probed 225 responses across 24 paths |
| focused container tests | PASS | 66 passed, 1 warning |
| `check_container.py` | PASS | non-root, read-only app layer, writable data volume, ready, restart |
| `smoke_container.py` | PASS | liveness, readiness, registration, authorized read, credit in history and balance, denied requests with no state change |

Docker state: `docker ps -a` empty before and after; the two existing volumes unchanged; the engine still responded. The scripts left their per-run images (`abm-check:ae4fb62d`, `abm-smoke:14a6ea56`), as earlier runs did; the Tester removed nothing.

## Findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| D-1 | Minor | `HANDOVER.md` named an old candidate head (`5d149d8`). | Fixed: the version table names `d11db54` as the tested revision. |
| D-2 | Minor | `HANDOVER.md` had no rows for the final-gates run and this reproduction, and its "documentation only" note stopped at `169f373`. | Fixed. |
| D-3 | Minor | `TASK-38-final-gates.md` said the Tester reproduction was pending. | Fixed. |
| D-4 | Minor | `TASK-38.md` "Next safe action" and the Tester scope note were out of date. | Fixed. |
| D-5 | Minor | The evidence file says 195 files formatted; the Tester saw 196. | Not a discrepancy. `ruff format --check` counts `.py` and `.md` files: 195 at `9f1d74e`, 196 at `d11db54` (the new evidence file is one more `.md`). Explained in the evidence file. |
| D-6 | Observation | pytest took 388.63 s here and 403.68 s in the author's run. | None needed. |

The Tester also found the CI situation described consistently across DV-05, `HANDOVER.md`, the work item, the reports and the CHANGELOG, with no document saying CI is green without the caveat; every recovery term carries a disclaimer; the contract is not linked from the private Specs repository; and no secrets or real data.

## Not verified by the Tester

Python 3.12.15 on Linux; hosted CI; the Docker Desktop app version and WSL2 backend; the Windows runbook steps, the Docker-stopped case and the cold build (out of scope for this pass, covered by `TASK-38-tester-report.md` and `TASK-38-tester-report-2.md`). The Tester's secrets review of the documents was limited to the validator's patterns and targeted reading. Synthetic data only; no production, backup, restore or recovery claim.
