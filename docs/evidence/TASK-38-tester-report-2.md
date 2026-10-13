# TASK-38 Tester report (independent pass on the merged revision)

**Task:** TASK-38 local handover (DEC-0086). **Merged commit:** `169f373fee22aaf9444cba9ed91e179818b463ea` (PR #154). **Specs:** `v1.9.18` / `507719611c79425fdcfd63d0f5897aed66655db7`. **Date:** 2026-10-13. **Role:** fresh-context Claude Code subagent, read-only on the project, working in a fresh clone outside OneDrive. It did not write the TASK-38 changes. It is a separate context from the author but the same model family, not a human tester. Scope: `docs/work-items/TASK-38.md`, section "Tester scope".

**Verdict: PASS within the stated scope.** No Blocker or Major finding. Two gates are not verified by the Tester (below).

## Environment

| Item | Value |
|---|---|
| Windows | 11 Home 10.0.26300 |
| Docker engine and client | 29.8.2 |
| `docker info` OS and driver | `Docker Desktop` / `overlayfs` |
| WSL2 backend | Not confirmed (`docker info` does not name it; `wsl -l -v` lists no distributions) |
| Docker Desktop app version | Not captured |
| Python | 3.12.10 (repository pin 3.12.15; Windows, not Linux CI) |

## Runbook steps (sections 1 to 4 and 6)

| Step | Result |
|---|---|
| Port 8000 free; clone and checkout `169f373` (`SPEC_VERSION` v1.9.18) | Pass |
| `docker build -t abm:local .` | Pass (all layers cached; not a cold build) |
| `docker run` per runbook | Pass; port bound to `127.0.0.1:8000`; read-only root filesystem; user 10001 |
| `/health/ready`, `/health/live` | Pass after a 4 s wait (see O-01) |
| `docker ps`, `docker logs` | Pass; JSON lines, no access-log lines |
| Register `acct-demo`, read it | Pass; `created`; `open`; balances 0 |
| Same registration POST | Pass; `meta.replayed: true` |
| Call without headers | Pass; HTTP 401 `UNAUTHORIZED` |
| `docker stop`, `docker start` | Pass; data kept |
| `docker stop`, `docker rm`, `docker run` on the same volume | Pass; data kept |
| `ABM_TRUSTED_INGRESS=false` | Pass; `CONFIG_INVALID: ABM_TRUSTED_INGRESS`, exit 1 |
| Port 8000 busy, second container | Pass; `port is already allocated` |
| Port 8000 busy, Windows process | Message differs from the runbook (F-03) |
| Container name in use | Pass; message matches the table |
| `docker image inspect abm:local --format '{{.Id}}'` | Pass; `sha256:213909ce356790e776c9b0647c82f1ce85ba9983548cf7d028c5934ef8c35349` (build-specific) |
| Reset command | Pass |

**O-01 reproduced.** The first `/health/ready`, under a second after `docker run`, failed with a send error. `docker ps -a` then showed the container `Up Less than a second`. The logs show only the later ready and live requests, so the failed call never reached the application. The probable cause is a startup race; it is not proven beyond that. After 4 s the call succeeded, so the runbook's wait-and-retry note is right.

## Gates (fresh clone)

| Gate | Result |
|---|---|
| `ruff check .` | passed |
| `ruff format --check .` | 193 files formatted |
| `mypy src harness tests scripts` | no issues, 102 files |
| `pytest -q -p no:cacheprovider` | 1325 passed, 1 warning |
| `validate_governance.py`, `validate_toolchain.py` | passed |
| `check_container.py`, `smoke_container.py` | **Not verified.** Docker Desktop stopped during the run and could not be restarted in time. Not a code failure. These passed in the author's local run on the PR #154 head (see `TASK-38-tester-report.md`). |

## Scope review

- `git diff df14a95 169f373 --stat`: `CHANGELOG.md`, `docs/evidence/TASK-38-tester-report.md`, `docs/handover/local-windows-runbook.md`. No change under `src/`, `Dockerfile`, `migrations/` or `.github/`.
- The runbook no longer links the private Specs repository. Backup, restore, disaster recovery, RPO, RTO and production appear only with a disclaimer. No secrets or real data.
- Section 5 settings match `.env.example` and `src/abm/config.py`. "Web access log off" is confirmed (`--no-access-log`, SEC-09).

## Findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| F-01 | Minor | Runbook quoted the `dockerDesktopLinuxEngine` pipe; the Tester saw `docker_engine`. | Fixed: row matches `failed to connect to the docker API`. |
| F-02 | Minor | Work item still Draft with stale completion text; no `HANDOVER.md` or tag. | Completion text updated; Verified, `HANDOVER.md` and tag come later. |
| F-03 | Minor | A non-Docker process on port 8000 gives `ports are not available ... bind`; a failed `docker run --name abm` leaves a stopped `abm`. | Fixed in section 7. |
| F-04 | Minor | Section 1 asserted the WSL2 backend, not confirmable. | Fixed: "default WSL2 backend is expected; the checks do not depend on it". |
| F-05 | Observation | README says the container check is "not verified locally". | Open, optional. |
| F-07 | Observation | "Quitting Docker Desktop stops `abm`" not re-verified by the Tester. | JDC observed it (`TASK-38-tester-report.md`, O-03). |

## Not verified by the Tester

`check_container.py` and `smoke_container.py` on the merged revision; the WSL2 backend and Docker Desktop app version; the Docker-stopped case and restart persistence (JDC ran them); a cold build (JDC ran one); Python 3.12.15 on Linux; any CI result (billing block). Synthetic data only; no production, backup, restore or recovery claim.
