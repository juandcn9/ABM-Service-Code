# Work item: TASK-02 — pin the reproducible toolchain

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-02`; `SEC-11`; `NFR-09`; `TEST-27`
- Decision, gap, or risk records: no new decision, gap, or risk; approved toolchain only
- Owner role: Builder; Codex is the execution runtime, and final verification requires an independent Tester

## Scope

- Objective: pin Python 3.12, direct and transitive runtime/development dependencies, lock generation, and the future container base reproducibly.
- Included files/components: Python/version metadata, exact dependencies, hash locks, official container digest, safe example configuration, dependency policy, and offline validation.
- Explicit exclusions: package/module layout, application code, runtime configuration parsing, database/API implementation, Dockerfile, image build, CI-gate expansion, deployment, credentials, and real data.
- Dependencies and entry gate: merged `TASK-01` at Code merge `a61319842567d859a7b2fd5f68b06690e40e6fd8`.

## Acceptance evidence

- Focused checks: `python scripts/validate_toolchain.py` and `python scripts/validate_governance.py` pass from repository root.
- Reproducibility: clean Python 3.12 environments install each lock using `--require-hashes --only-binary=:all:`.
- Supply chain: direct pins match `pyproject.toml`; every resolved distribution is exact and hashed; the official Python container index is digest-pinned.
- Security/configuration: service runtime performs no dependency download, `.env.example` contains no secret, and the baseline declares no required secret.

## Implementation notes

- Dependency versions and the container digest were checked against official upstream metadata on 2026-10-09.
- `pip-tools==7.6.2` is a build-time lock generator only, not a runtime dependency.
- Ponytail is not applicable to this Codex runtime.

## Completion

- Code commit/PR: the exact reviewed branch commit and PR are the GitHub record.
- Checks/results: lock validation, clean installs, existing governance CI, exact-head CI, and independent review are required before merge.
- Review findings/resolution: recorded in the PR; all actionable findings must be resolved and reverified.
- Residual risks: future dependency vulnerabilities require a controlled update PR; no automatic update is authorized.
- Next safe action: begin `TASK-03` only after this exact `TASK-02` revision is merged.
