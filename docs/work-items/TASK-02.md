# Work item: TASK-02 — pin the reproducible toolchain

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-02`; `SEC-11`; `NFR-09`; `TEST-27`
- Decision, gap, or risk records: no new decision, gap, or risk; approved toolchain only
- Owner role: Builder; Codex is the execution runtime, and final verification requires an independent Tester

## Scope

- Objective: pin Python 3.12, direct and transitive runtime/development dependencies, lock generation, and the future container base reproducibly.
- Included files/components: Python/version metadata, exact dependencies, hash locks including the generator/bootstrap graph, official container digest, safe example configuration, dependency policy, and offline validation.
- Explicit exclusions: package/module layout, application code, runtime configuration parsing, database/API implementation, Dockerfile, image build, CI-gate expansion, deployment, credentials, and real data.
- Dependencies and entry gate: merged `TASK-01` at Code merge `a61319842567d859a7b2fd5f68b06690e40e6fd8`.

## Acceptance evidence

- Focused checks: `python scripts/validate_toolchain.py` and `python scripts/validate_governance.py` pass from repository root.
- Reproducibility: clean Python 3.12 environments install each lock using `--require-hashes --only-binary=:all:`.
- Supply chain: direct pins match `pyproject.toml`; every resolved distribution and lock-generation dependency is exact and hashed; the official Python container index is digest-pinned.
- Security/configuration: service runtime performs no dependency download, `.env.example` contains no secret, and the baseline declares no required secret.

## Implementation notes

- Dependency versions and the container digest were checked against official upstream metadata on 2026-10-09.
- `pip-tools==7.6.2` and its bootstrap graph are development/build-time dependencies only and are installed through the development lock, never the runtime lock.
- Ponytail is not applicable to this Codex runtime.

## Completion

- Code commit/PR: the exact reviewed branch commit and PR are the GitHub record.
- Checks/results: lock validation, clean installs, existing governance CI, exact-head CI, and independent review are required before merge.
- Review findings/resolution: recorded in the PR; all actionable findings must be resolved and reverified.
- Residual risks: future dependency vulnerabilities require a controlled update PR; no automatic update is authorized.
- Next safe action: begin `TASK-03` only after this exact `TASK-02` revision is merged.

## Independent verification

- Role and context: Tester, a fresh-context agent that did not implement `TASK-02`, launched by Claude Code on 2026-10-09. The sanitized report is committed at [`docs/evidence/TASK-02-tester-report.md`](../evidence/TASK-02-tester-report.md); the Builder only reformatted it.
- Revision tested: Code `c768c70a8599d2ea8ba0675447ca36f4c2ad15cf` (content commits `bb36e0a`, `bb539ae`) against Specs `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Environment: Python 3.12.10 on Windows in throwaway virtual environments; no container runtime. Exact Python 3.12.15 has no Windows binary, so nothing was executed on it.
- Result: PASS with findings; zero Blocker, zero Major.
- Verified: version and pin agreement; runtime/development separation; all 35 locked name==version pairs exist unyanked on PyPI and every published file hash is present; clean `--require-hashes --only-binary=:all:` installs of both locks with clean `pip check`; byte-identical lock regeneration; a tampered hash is refused; `validate_toolchain.py` fails on each of ten injected mutations; the container digest equals the official Docker Hub manifest digest for `python:3.12.15-slim-bookworm`; no Dockerfile, binary, or secret; no runtime installs (`NFR-09`); safe example configuration (`TEST-27`, example-configuration half).
- Not verifiable here: behavior on exactly 3.12.15; Linux lock regeneration; an actual container build; the `TEST-27` required-secret-startup half (no application code exists and the baseline declares no required secret); the exact-head CI result of the original PR was not inspected by the Tester (the `validate-governance` runs on `bb539ae` and `c768c70` succeeded, and that CI runs only the governance validator, see F1).
- Minor findings, scheduled for `TASK-04` (not waived; no risk acceptance is recorded or needed; no Specs change):
  - F1: CI does not run `validate_toolchain.py` and does not pin Python 3.12.15 — to be addressed in `TASK-04`.
  - F2: `validate_toolchain.py` compares against its own constants and a whole-file digest and does not cross-check the locks against `pyproject.toml` — to be reviewed in `TASK-04`.
  - F3: `validate_governance.py` skips `.venv` and cache directories in its secret scan; they are git-ignored — to be reviewed in `TASK-04`.
- Scope of "Verified": it covers the `TASK-02` acceptance evidence listed above only. The `TEST-27` required-secret-startup half remains open for the first task that introduces application configuration.
- Observations, with their status:
  - F4 (Tester Observation): the development lock was generated on Windows (`colorama` is unconditional); Linux regeneration was not tested. Scheduled. Owner Builder. Trigger: the next change to `requirements-dev.lock`.
  - F5 (Tester Observation): `.gitignore` omits `venv/` and `env/`. Resolved by TASK-04 (commit `24cbc43`; `.gitignore` lines 17-18 on `main`).
  - Other observations, since resolved: `.gitattributes` (LF normalization) was added by TASK-04; the 'no image build exists yet' observation is closed by TASK-27 (container build and run in CI).
