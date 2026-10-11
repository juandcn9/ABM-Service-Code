# Work item: TASK-36 — black-box HTTP smoke check against the running container image

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.12` / `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f` (Code pin). Specs `main` is at `857092a` (TASK-36 entry and DEC-0069; TASK-35 depends on TASK-36 and DEC-0070).
- TASK and affected IDs: `TASK-36`; `DEC-0067` (the smoke check is a planned follow-up, minimum scope listed there); `DEC-0069` (why it is a numbered task); `DEC-0070` (TASK-36 may start after TASK-27; TASK-35 depends on it); `TEST-31`; `TEST-33`.
- Dependencies: `TASK-27` (Verified; PR #104 merged `772ee1f`, record PR #107).
- Owner role: Builder (Claude Code); independent Tester verification of the merged head is required.

## Scope

- Objective: prove, against the image that CI builds, that the deployed HTTP API works end to end in its minimum form: liveness and readiness, account registration, an authorized account read, one representative money-changing instruction visible in history, and one denied request with no state change.
- Included:
  1. `scripts/smoke_container.py`: builds the image (through `check_container.py` helpers), starts it with a fresh volume and a read-only root filesystem, and runs the probes over HTTP. Standard library only.
  2. `run_smoke(call)` in that script: the probe sequence, written against a call adapter so the same steps run over HTTP in CI and in-process in tests. It returns the list of failures; an empty list is a pass.
  3. Probes (minimum from DEC-0067):
     - `GET /health/live` and `GET /health/ready` return 200 on a fresh volume.
     - `POST /v1/accounts/registrations` by `account_registrar` returns 201.
     - `GET /v1/accounts/{id}` by `account_reader` with the exact account scope returns 200 with the registered account.
     - One money-changing instruction: an incoming ACH notice by `payment_orchestrator` (201), then its settlement (200). The credit is then visible in `GET /v1/accounts/{id}/transactions` (200, one credit of the notice amount) and in the balance.
     - One denied request: `GET /v1/accounts/{id}` with no caller context returns 401 `UNAUTHORIZED`; a registration by a role without that permission returns 403; the balance and history are unchanged afterwards.
  4. Test: `tests/integration/test_smoke_probes.py` runs `run_smoke` against the in-process app (`app_from_environment` on a fresh database) and expects no failures, plus one case where a deliberately broken call adapter (wrong status) is reported as a failure.
  5. CI: a step in the existing `container-check` job runs `scripts/smoke_container.py` after `check_container.py`.
- Explicit exclusions:
  - Restart continuity and recovery (TASK-28, TASK-29), the full demonstration scenario (TASK-31), and any new route or behaviour.
  - Load, concurrency, or timing claims.
  - Release gating (TASK-35 depends on this task per DEC-0070; the gate is enforced by the Specs dependency, not by this code).

## Acceptance evidence

- Focused tests: `tests/integration/test_smoke_probes.py` passes; the adapter-failure case proves that a wrong status is reported.
- Required broader gates: full pytest, ruff check and format, mypy, both validators, and the `container-check` CI job (which now includes the smoke step) on the exact PR head.
- Failure cases: a missing or wrong status at any probe is reported by name; a denied request that changes state is reported.
- Documentation and trace updates: this work item; the README container section names the smoke step.

## Implementation notes

- The probes use only documented contract fields (the same bodies as the Code's own HTTP tests). No new public behaviour.
- The check runs as a Builder-owned script; it is not a Tester pass. Tester verification of the merged head follows the lifecycle.

## Non-claims (until implemented and tested)

- No load, throughput, concurrency, backup, restore, or disaster-recovery claim.
- The smoke check covers the minimum scope of DEC-0067 only; it is not the full scenario of TASK-31.

## Completion

- Code commit/PR: branch `feat/task-36-smoke` from `main` `01b2cf5`; PR not yet opened.
- Commands/checks and results: pending.
- Review findings/resolution: pending.
- Residual risks: the CI runner's container engine; the smoke check uses the CI-built image only; no claim beyond the probes listed.
- Next safe action: implement the probe script and its in-process test, then open the Code PR.
