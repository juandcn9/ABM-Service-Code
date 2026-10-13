# ABM local service: handover record v0

**Status:** Verified

This is the handover record for the tag `handover-v0.1`. TASK-38 is Verified (Specs DEC-0087, in Specs release `v1.9.19`). Hosted CI did not run; see "Conditions met at tagging" and deviation DV-05.

## What is handed over

A local, single-computer run of the ABM service (Account Balances Management Service) on Windows with Docker Desktop, using synthetic data only. The guide is [`local-windows-runbook.md`](local-windows-runbook.md). The authority is DEC-0086 and TASK-38.

To get this version: clone the Code repository, run `git checkout handover-v0.1`, and follow the runbook.

## Version

| Item | Value |
|---|---|
| Code tag | `handover-v0.1`, created on 2026-10-13 on the merge commit of the pull request that adds this record. Read the commit with `git rev-parse handover-v0.1^{commit}`. |
| Code commit lineage | JDC approved Code `46feb9d03c4eb5f07c304f2f84445a73df193ec5` on 2026-10-13 and asked for this record to be finalised before tagging. The tagged commit differs from `46feb9d` by this record (this file, the TASK-38 work item completion lines and a CHANGELOG line) and nothing else. The gates were run by the author on `9f1d74e739712842b4d05b1d0da8236ea012e3fb` and reproduced by the Tester on `d11db540e3ef5ca057249bd98a18ba729cfa65b8`; both differ from the tagged commit by documentation only. |
| Specs release implemented | `v1.9.18`, commit `507719611c79425fdcfd63d0f5897aed66655db7` (also in `SPEC_VERSION`). Specs `v1.9.19` (commit `8eb6499f7c78b5bbce658162e030db4641e800e9`) is a status-record-only release that adds DEC-0087 (TASK-38 Verified); it changes no requirement, contract or behavior, and the Code pin stays at `v1.9.18`. |
| OpenAPI contract | `contracts/openapi.yaml` of Specs `v1.9.18`. The owner sends it separately; the Specs repository is private. |
| Image | Built locally with `docker build -t abm:local .`. The image identifier differs between builds of the same commit (observed: cached build, cold build, and the Tester's build gave different values), so it is recorded per run, not as a fixed value. Cold build by JDC: `sha256:d52e2ce0b0fe760cc59a1dbc999e89caab7a9f37f1ab2a77198066a2d5c90ab8`. Tester build: `sha256:213909ce356790e776c9b0647c82f1ce85ba9983548cf7d028c5934ef8c35349`. The base image is pinned by digest in the Dockerfile. |
| Owner and support | JDC. Internal use only; no licence file. |

## What was verified, and where

| Evidence | Revision | Result |
|---|---|---|
| Clean Windows run by JDC, outside OneDrive ([`TASK-38-tester-report.md`](../evidence/TASK-38-tester-report.md)) | `df14a95` | Build (cached and `--no-cache`), start, readiness, register, read, replay, 401, restart and removal on the same volume, wrong ingress, busy port, Docker Desktop quit and restart: all as the runbook says |
| Local gate run by the author while CI was blocked (same report) | PR #154 head `cbf6beb` | Governance, ruff, format, mypy, 1325 tests, HTTP conformance (225 responses), container check, smoke: passed |
| Independent Tester pass ([`TASK-38-tester-report-2.md`](../evidence/TASK-38-tester-report-2.md)) | `169f373` | Runbook sections 1 to 4 and 6 and all local gates passed; verdict "pass within the stated scope" |
| Final gate run by the author, the DV-05 substitute ([`TASK-38-final-gates.md`](../evidence/TASK-38-final-gates.md)) | `9f1d74e` | Governance and toolchain validators, ruff, format, mypy, 1325 tests, HTTP conformance, container check, smoke: all passed |
| Independent reproduction of the final gates ([`TASK-38-final-gates-tester-report.md`](../evidence/TASK-38-final-gates-tester-report.md)) | `d11db54` | Every gate passed again, including the container check and smoke; documentation verdict pass with Minor findings, since fixed |

Changes after `169f373` are documentation only: the Tester reports and scope, the runbook wording fixes, deviation DV-05, the final-gates evidence and its Tester reproduction, and this record.

## Stated limits

- Synthetic data only; one service process and one SQLite volume; no production identity or public ingress; no live partner connection. Not production ready.
- Restart against the intact volume is the only recovery covered. There is no backup, restore, disaster recovery, RPO or RTO claim.
- The service trusts caller headers from a trusted ingress. Never expose it to untrusted callers or the internet.
- No hosted CI ran on any TASK-38 revision (GitHub Actions billing block). JDC accepted the risk (DV-05). The gates were run locally on Windows with Python 3.12.10, not on the Linux CI runner with 3.12.15; the container scripts run the service on the pinned 3.12.15 image. The Testers were fresh-context Claude Code agents, not humans, and the runs have no hosted status.
- Not verified by a Tester (see the Tester scope in [`TASK-38.md`](../work-items/TASK-38.md)): the WSL2 backend and the Docker Desktop app version (read afterwards from the author's machine: Docker Desktop 4.95.0, WSL distro `docker-desktop` version 2); a cold build, the Docker-stopped case and restart persistence (run by JDC only).
- First request right after `docker run` can be reset for a few seconds while the service starts. Wait and retry; the runbook says so.
- The runbook commands are not run by CI on Windows.

## Conditions met at tagging

1. Hosted CI evidence does not exist (GitHub Actions has not run since 2026-10-13). JDC accepted the risk of tagging without it (DV-05, `docs/governance/deviations.md`). The substitute, a local run of the CI gates plus the container and smoke checks, was reproduced by a fresh-context Tester on `d11db54`. When GitHub Actions runs again, a green run on `main` closes DV-05.
2. `check_container.py` and `smoke_container.py` passed on `9f1d74e` (author) and `d11db54` (Tester) with a stable Docker engine.
3. TASK-38 is Verified in its work item (Code PR #159) and in the Specs (DEC-0087, Specs PR #78, release `v1.9.19`).
4. JDC approved Code `46feb9d` on 2026-10-13, and the tag `handover-v0.1` was created on the merge commit of the pull request that adds this record.

## Release notes (v0)

- First local handover: runbook, README scope and non-claims, handover tests, clean-run and Tester evidence.
- No change to the service code, image definition, migrations or CI workflow in this handover.
