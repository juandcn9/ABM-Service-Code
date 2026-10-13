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

## Non-claims

- Synthetic data only; one process and one SQLite volume; no production identity or public ingress; no live partner; no backup, restore, disaster recovery, RPO, or RTO.
- The commands in the runbook are not executed by CI on Windows.

## Completion

- Code commit/PR: branch `task-38-local-handover`; PR not yet opened.
- Next safe action: open the Code PR, then the clean Windows run, then the Tester pass.
