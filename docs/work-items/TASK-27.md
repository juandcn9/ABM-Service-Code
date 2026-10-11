# Work item: TASK-27 — non-root read-only container with one writable data mount

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.12` / `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f` (Code pin, PR #101). Specs `main` is at `d09bae1` (status file, PR #54); the requirements below are unchanged in it.
- TASK and affected IDs: `TASK-27`; `NFR-01`; `NFR-10`; `TEST-31`; `TEST-33`; `SEC-11` (pinned base image and dependencies); `NFR-08` (no backup or recovery claim, guarded by TEST-32 in TASK-29).
- Specs references: `specs/07-operations-and-recovery.md` sections 5 (demonstration container mounts one named volume and sets `ABM_DB_PATH` inside it) and 10 (single documented command set); configuration table in section 2 (`ABM_MODE`, `ABM_DB_PATH`, `ABM_LOG_LEVEL`, `ABM_BUSY_TIMEOUT_MS`, `ABM_TRUSTED_INGRESS`, `ABM_CLOCK_MODE`).
- Decision, gap, or risk records: DEC-0055 (one shared SQLite connection; single process; no throughput claim); DEC-0056 (conformance evidence is script-run; CI execution of it belongs to TASK-27); TASK-25 and TASK-26 scheduled items listed below.
- Dependencies: `TASK-25` (Verified) and `TASK-26` (Verified: implementation PR #98, fixes PR #100 merged `d45e766`, Tester PASS on `d45e766`, Verified record PR #102 merged `0d02ad5`).
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.

## Scope

- Objective: a container image that runs the HTTP service as a non-root user, with the application layer read-only and one writable data volume, and a documented command set that starts it against a fresh volume and reaches readiness.
- Included (proposed):
  1. `src/abm/config.py`: parse the `ABM_*` settings above from the environment. Missing or invalid settings give `CONFIG_INVALID` at startup and name only the setting, never its value. `ABM_CLOCK_MODE` must be `system` in the demonstration container; `controlled` is refused there.
  2. `src/abm/main.py`: an ASGI factory `app_from_environment()` in the composition root that loads the settings, opens the database with `start_database`, and passes the real readiness check (`readiness_reasons`) to `create_app`. This wires the readiness check that TASK-25 and TASK-26 left as a scheduled item.
  3. `Dockerfile` and `.dockerignore`: base image pinned by digest from `toolchain.toml`; dependencies installed from `requirements.lock` with `--require-hashes` during the build only; a non-root user with a fixed numeric UID; `/data` as the only writable path (declared as `VOLUME`); the process started with `uvicorn --factory abm.main:app_from_environment --workers 1`.
  4. `scripts/check_container.py`: builds the image, starts it with a fresh named volume and with `--read-only`, waits for `/health/ready`, asserts the process UID is non-zero, that a write outside `/data` fails, that a write inside `/data` succeeds, and that a stop and restart on the same volume reaches ready again. Standard library only.
  5. CI: a job in `.github/workflows/` that runs `scripts/check_container.py` on the runner, which has a container engine.
  6. Tests: unit tests for the configuration parser (every required setting, each rejected value, names-only error text, `controlled` refused in the demonstration mode).
  7. **Decided (JDC, 2026-10-11):** CI runs `scripts/check_http_conformance.py` in-process on the exact Code revision (the PR head), against `contracts/openapi.yaml` at the pinned Specs commit, fetched with a read-only deploy key (`SPECS_DEPLOY_KEY`). The script stays as it is: it seeds its own database and uses `TestClient`, which gives exhaustive contract coverage; rewriting it for external HTTP is not part of TASK-27. Container-level HTTP behaviour is a separate follow-up (item 11).
  8. `scripts/check_container.py` copies the container's data directory out with `docker cp`, runs `scripts/scan_aged_items.py` (TASK-26, DEC-0063) on it with an explicit threshold, and checks that the manifest carries the exact commit and an image digest. The CI job passes the focused test summary. Scheduling beyond this CI run is out of scope.
  9. Container log check: `scripts/check_container.py` reads the container's stdout and asserts that structured events (TASK-26 sink, DEC-0062) appear with `ts` and `severity` (closes T2-7 in the container context).
  10. Manifest revision format (Tester F10, T2-5): `scripts/scan_aged_items.py` refuses `--spec-commit` and `--code-commit` values that are not 40-character lowercase hexadecimal SHAs, with a focused test for a short value, an uppercase value, and a non-hex value.
- Explicit exclusions:
  11. **Follow-up, separately owned (not in TASK-27 acceptance):** a black-box HTTP smoke check against the running container image. Acceptance: liveness and readiness return 200 and 503 correctly; account registration succeeds; an authorized account read returns the account; one representative money-changing instruction (for example an incoming ACH settlement) posts and is visible in history; one denied request (missing or wrong caller context) returns the contract error without state change. Owner: Builder; it needs its own work item and, if it counts as a TASK, a Specs entry.
  - Backup, restore, disaster recovery, RPO and RTO (NFR-08; TASK-29 verifies the absence of claims).
  - The demonstration run script and the full scenario (TASK-31), the restart continuity suite (TASK-28), and the AWS reference (TASK-30).
  - Production readiness beyond the single container (no load balancer, TLS, or secrets integration).
  - Changes to any application behavior or public route.

## Environment decision (recorded, reversible)

- The development workstation has no container engine (`docker` is not installed), so TEST-33 cannot run locally. The container gate runs in CI, on a runner with a container engine. Until that job passes on the PR head, TEST-33 is **not verified**, and the work item will say so. Choice recorded here so JDC can redirect it.
- The base image digest is the one already pinned in `toolchain.toml`. No new base image is introduced.
- Clock: the Specs table allows `controlled` in the demonstration mode. This container refuses it, because a container serving real time has no test harness to control the clock. This is stricter than the table, recorded here so JDC can redirect it.

## Acceptance evidence

- Focused tests: configuration parser unit tests; `app_from_environment()` builds an app whose readiness reports `DATABASE_UNAVAILABLE` when the path is unusable and ready when the database starts; the manifest SHA format test (item 10).
- Required broader gates: pytest, ruff check and format, mypy, both validators, and the container check job in CI on the exact head.
- Failure, concurrency, authorization, and recovery cases: missing setting, malformed setting, `controlled` clock in demonstration mode, unwritable data directory, non-root and read-only assertions, and restart on the same volume (TEST-33 restart clause).
- Documentation and trace updates: this work item; `README.md` demonstration command set; `docs/governance/dependencies.md` note that the image build is the only installation step.

## Scheduled items carried into TASK-27

- Wire a real readiness check to the entry point (TASK-25 and TASK-26 scheduled item): covered by item 2 above.
- Manifest revision check (Tester F10 and T2-5): covered by item 10. `scripts/scan_aged_items.py` refuses `--spec-commit` and `--code-commit` values that are not 40-character lowercase hexadecimal SHAs. The CI job (item 8) passes the exact `GITHUB_SHA` and the Specs SHA from `SPEC_VERSION`. Owner Builder.
- Structured events without a sink (T2-7): covered by item 9. The container writes events to stdout; the check reads them back.
- CI execution of the TASK-25 conformance script (`scripts/check_http_conformance.py`, DEC-0056): covered by item 7.

## Implementation notes

- Single worker: one shared SQLite connection behind one process-local lock (DEC-0055). `--workers 1` is required; a higher count would break the serialization claim.
- The image runs with `--read-only` root filesystem; `/tmp` is not required by uvicorn in this configuration, so no tmpfs is mounted. If the check finds a required writable path, it is recorded here, not silently mounted.
- The data directory and the database path are the same mounted directory; `ABM_DB_PATH` is set to a file inside `/data`.
- Readiness runs the real check (`readiness_reasons`) on every probe, not once at startup. A database that cannot open starts the service unready behind `UnavailableUnitOfWork`, which answers `SERVICE_UNREADY` to every read and write (NFR-02, no partial effect).
- Structured events go to stdout at every `ABM_LOG_LEVEL`. The level is validated but does not filter events yet (limit).
- `scripts/validate_governance.py` pins the CI workflow digest (`EXPECTED_WORKFLOW_SHA256`); the workflow change updates it in the same commit, as the validator requires.
- The Specs contract is read from the pinned Specs commit in CI. This repository has no `contracts/` directory.

## Non-claims (until implemented and tested)

- No backup, restore, disaster recovery, RPO, or RTO claim (NFR-08).
- No claim that the container is production-ready, has TLS, or is behind an authenticated ingress. Trusted ingress is a deployment responsibility (SEC-01).
- No throughput or concurrency claim beyond the single-process boundary (DEC-0055).

## Completion

- Code commit/PR: implementation PR #104 (branch `feat/task-27-container`), head `b5d240b`; not yet merged.
- Commands/checks and results: full pytest on `b5d240b`: 987 passed. Focused tests (config, check decision, container entry, observability): pass. `scripts/check_container.py` reports "not run" on this workstation (no container engine). CI on `b5d240b`: `container-check` passed (TEST-33 evidence: non-root, read-only root filesystem, writable data volume, ready, restart, manifest); `quality-gates` and `validate-governance` passed; `http-conformance` fails only because the CI token cannot read the private Specs repository.
- Access decision (JDC, 2026-10-11): read-only deploy key on the Specs repository, stored as `SPECS_DEPLOY_KEY` in the Code repository; the conformance job checks out the PR head explicitly and verifies the fetched Specs commit equals `1f6a26d`.
- Review findings/resolution: fresh-context review of `748449c` raised three Majors and several Minors. Fixed in `b5d240b`: access log off (`--no-access-log`); read-only root filesystem asserted from the engine; scope item 7 kept as in-process conformance, a reduction needing JDC confirmation (open). Minors fixed: clock refused other than system; busy-timeout length bounded; startup failure keeps real reason codes; Dockerfile header; CI checks out the PR head. Re-review of `b5d240b`: CLEAN, no open Blocker or Major. Minor gap open: no integration test for the real startup reason codes (only the DATABASE_UNAVAILABLE path is covered).
- Residual risks: TEST-33 depends on the CI runner's container engine; `http-conformance` needs Specs read access; the image digest in the manifest is the base-image pin; `ABM_LOG_LEVEL` does not filter events; no backup or recovery claim (NFR-08).
- Next safe action: JDC approves the exact head of PR #104 (after deciding scope item 7 and the Specs access for `http-conformance`), then merge, then the Tester pass on the merged head.
