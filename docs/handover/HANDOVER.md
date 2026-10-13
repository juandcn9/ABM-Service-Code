# ABM local service: handover record v0

**Status:** Draft

This is not a handover until every item under "Conditions before the tag" is done. TASK-38 is not Verified. Fields that depend on those items say so.

## What is handed over

A local, single-computer run of the ABM service (Account Balances Management Service) on Windows with Docker Desktop, using synthetic data only. The guide is [`local-windows-runbook.md`](local-windows-runbook.md). The authority is DEC-0086 and TASK-38.

## Version

| Item | Value |
|---|---|
| Code tag | `handover-v0.1`, not created yet. Created only after JDC approves the exact commit. |
| Code commit | To be set at tagging. Candidate head at drafting: `5d149d86e0387730bc4800630ec7765c6af837ff` (the evidence is for earlier commits, see below). |
| Specs release | `v1.9.18`, commit `507719611c79425fdcfd63d0f5897aed66655db7` (also in `SPEC_VERSION`) |
| OpenAPI contract | `contracts/openapi.yaml` of that Specs release. The owner sends it separately; the Specs repository is private. |
| Image | Built locally with `docker build -t abm:local .`. The image identifier differs between builds of the same commit (observed: cached build, cold build, and the Tester's build gave different values), so it is recorded per run, not as a fixed value. Cold build by JDC: `sha256:d52e2ce0b0fe760cc59a1dbc999e89caab7a9f37f1ab2a77198066a2d5c90ab8`. Tester build: `sha256:213909ce356790e776c9b0647c82f1ce85ba9983548cf7d028c5934ef8c35349`. The base image is pinned by digest in the Dockerfile. |
| Owner and support | JDC. Internal use only; no licence file. |

## What was verified, and where

| Evidence | Revision | Result |
|---|---|---|
| Clean Windows run by JDC, outside OneDrive ([`TASK-38-tester-report.md`](../evidence/TASK-38-tester-report.md)) | `df14a95` | Build (cached and `--no-cache`), start, readiness, register, read, replay, 401, restart and removal on the same volume, wrong ingress, busy port, Docker Desktop quit and restart: all as the runbook says |
| Local gate run by the author while CI was blocked (same report) | PR #154 head `cbf6beb` | Governance, ruff, format, mypy, 1325 tests, HTTP conformance (225 responses), container check, smoke: passed |
| Independent Tester pass ([`TASK-38-tester-report-2.md`](../evidence/TASK-38-tester-report-2.md)) | `169f373` | Runbook sections 1 to 4 and 6 and all local gates passed; verdict "pass within the stated scope" |

Changes after `169f373` are documentation only (the Tester report, the Tester scope, three runbook wording fixes, and this record).

## Stated limits

- Synthetic data only; one service process and one SQLite volume; no production identity or public ingress; no live partner connection. Not production ready.
- Restart against the intact volume is the only recovery covered. There is no backup, restore, disaster recovery, RPO or RTO claim.
- The service trusts caller headers from a trusted ingress. Never expose it to untrusted callers or the internet.
- Not verified by the Tester (see the Tester scope in [`TASK-38.md`](../work-items/TASK-38.md)): the WSL2 backend and the Docker Desktop app version (read afterwards from the author's machine, not by the Tester: Docker Desktop 4.95.0, WSL distro `docker-desktop` version 2); a cold build, the Docker-stopped case and restart persistence (run by JDC only); Python 3.12.15 on Linux (local runs used 3.12.10 on Windows); `check_container.py` and `smoke_container.py` on the merged revision (they passed in the author's run, not the Tester's).
- First request right after `docker run` can be reset for under a few seconds while the service starts. Wait and retry; the runbook says so.
- The runbook commands are not run by CI on Windows.

## Conditions before the tag

1. Green GitHub Actions on the exact commit to be tagged. While deviation DV-05 (`docs/governance/deviations.md`) is open, the accepted substitute is an attested local CI run of that commit (`scripts/ci_local.py`, not written yet) in the pinned Linux container, reproduced by the Tester. This record then states which of the two applies.
2. `check_container.py` and `smoke_container.py` pass on that commit with a stable Docker engine.
3. TASK-38 is set to Verified, with the Specs status record updated.
4. JDC approves the exact commit, and the tag `handover-v0.1` is created on it. This record is then updated with the commit, the CI run and the date.

## Release notes (v0)

- First local handover: runbook, README scope and non-claims, handover tests, clean-run and Tester evidence.
- No change to the service code, image definition, migrations or CI workflow in this handover.
