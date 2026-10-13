# Work item: TASK-38 — Local Service Handover v0 (Windows, Docker Desktop)

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.18` / `507719611c79425fdcfd63d0f5897aed66655db7` (Code pin, PR #152).
- TASK and affected IDs: `TASK-38`; `DEC-0086`; `NFR-01`, `NFR-08`; `TEST-31`, `TEST-32`, `TEST-33`.
- Dependencies: `TASK-27`, `TASK-29`, `TASK-36` (all Verified). Not a prerequisite of `TASK-35`; `TASK-31` to `TASK-35` are excluded.
- Owner role: Builder (Claude Code); independent Tester verification of the merged head and a clean Windows run are required.

## Scope

- Objective: a technical requestor on Windows can clone this repository at one tag, build the existing image with Docker Desktop (WSL2), run it on `127.0.0.1`, and operate it from one short guide.
- Included:
  1. `README.md`: the stale "no API route or built container" statement replaced by the current scope; the repository map points at `docs/work-items/` and the runbook.
  2. `docs/handover/local-windows-runbook.md`: prerequisites, build, start, readiness, status, logs, stop, restart, warned local-data reset, configuration, trust boundary, API entry point, version, owner, limits.
  3. `tests/unit/test_handover_docs.py`: the runbook exists, is linked from the README, and carries the trust-boundary warning and the documented start settings.
  4. `docs/handover/HANDOVER.md`: the handover record (Code tag, Specs release, image identifier, clean-run result), written when the clean run passes.
- Explicit exclusions:
  - No change under `src/`, the Dockerfile, migrations, or the CI workflow.
  - TASK-31 to TASK-35, production claims, other container engines, native (non-container) runs.

## Acceptance evidence

- Focused tests: `tests/unit/test_handover_docs.py`; `tests/unit/test_recovery_claims.py` covers the new documents.
- Required broader gates: both validators, ruff check and format, `mypy src harness tests scripts`, full pytest, CI on the exact PR head.
- Manual (JDC, Windows with Docker Desktop): the runbook run verbatim from a fresh clone, recorded in `docs/evidence/TASK-38-tester-report.md`.

## Tester scope (approved by JDC, 2026-10-13)

The independent Tester verifies, on the merged revision, what a Windows machine with Docker Desktop can show without quitting or reconfiguring it:

- In scope: the runbook sections 1 to 4 and 6 run verbatim from a fresh clone; the failure cases that need no change to Docker Desktop (wrong `ABM_TRUSTED_INGRESS`, port 8000 busy, name in use); persistence across stop, start and container removal; the local gates (ruff, format, mypy, full pytest, both validators); the scope and non-claims review of the TASK-38 diff.
- Out of scope, so not a pass criterion, and each stated as a limit in the evidence and in `HANDOVER.md`: the WSL2 backend and the Docker Desktop app version (not shown by `docker info`); the Docker-stopped case and persistence across a Docker Desktop restart (need Docker Desktop to be quit; JDC ran them, see `TASK-38-tester-report.md`); a cold no-cache build (JDC ran one); Python 3.12.15 on Linux (local runs use 3.12.10 on Windows); any GitHub Actions result while CI is billing-blocked.
- Container scripts: `check_container.py` and `smoke_container.py` need a stable Docker engine for several minutes. They passed in the author's local run on the PR #154 head, which differs from the merged revision only by an evidence commit. They stay unverified by the Tester unless run, and the verdict must say so.
- The verdict is therefore "pass within the stated scope", never an unqualified pass. GitHub CI is billing-blocked; JDC accepted the risk of tagging `handover-v0.1` without hosted CI verification (DV-05), with the local gates and the Tester reproduction as the substitute.

## Non-claims

- Synthetic data only; one process and one SQLite volume; no production identity or public ingress; no live partner; no backup, restore, disaster recovery, RPO, or RTO.
- The commands in the runbook are not executed by CI on Windows.

## Completion

- Code commit/PR: PRs #153 and #154 merged (`df14a95`, `169f373`).
- Clean Windows run by JDC and the Tester pass on `169f373`: recorded in `docs/evidence/TASK-38-tester-report.md` and `TASK-38-tester-report-2.md`.
- Next safe action: run the full gate set locally on the tag candidate and have the Tester reproduce it, write the results into `docs/handover/HANDOVER.md`, set this task to Verified, then tag on JDC's approval.
