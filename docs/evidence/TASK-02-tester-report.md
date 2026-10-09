# TASK-02 independent Tester report (sanitized record)

**Provenance:** final report returned by a fresh-context Tester agent on 2026-10-09, launched by the Claude Code session that built `TASK-03`. The Tester did not implement `TASK-02` (built by Codex). Content below preserves the report's findings and results; the Builder only reformatted it and replaced secret-shaped example strings with prose. It is evidence input, not Specs authority.

- Revision tested: Code `c768c70a8599d2ea8ba0675447ca36f4c2ad15cf` (first parent `a613198`; content commits `bb36e0a`, `bb539ae`), in a detached worktree.
- Specs: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Environment: Python 3.12.10 on Windows, throwaway virtual environments, read-only access to PyPI and Docker Hub metadata, no container runtime.
- Limitation: the pinned Python 3.12.15 has no Windows binary, so nothing ran on it. Local results are for series 3.12.

## Result

PASS with findings. Zero Blocker, zero Major.

## Checks

| # | Check | Result | Evidence summary |
|---|---|---|---|
| 1 | Version agreement | PASS | `.python-version` and `toolchain.toml` are 3.12.15; the container tag is `python:3.12.15-slim-bookworm` with a pinned digest; `requires-python` is `>=3.12,<3.13`. |
| 1b | Direct dependencies exact and separated | PASS | Runtime: fastapi 0.143.0, pydantic 2.14.0, uvicorn 0.54.0. Development: httpx, mypy, pip-tools, pytest, ruff, all `==`. Runtime lock has 14 packages and no development-only package. |
| 1c | `opentelemetry-api` in the runtime lock | PASS | It is an unconditional requirement of fastapi. |
| 2 | Lock hashes against PyPI | PASS | All 35 distinct name==version pairs exist and are not yanked; no lock hash is unknown to PyPI. |
| 2b | Hash coverage | PASS | Every published file hash (wheels and sdist, including manylinux/musllinux) is present, so the locks cover the Linux container. |
| 2c | Lock-generator graph hashed | PASS | The development lock has 35 packages including pip-tools 7.6.2, build, pyproject-hooks, click, packaging, pip, setuptools and wheel, all hashed. |
| 3 | Clean install, runtime lock | PASS | `pip install --require-hashes --only-binary=:all: -r requirements.lock` succeeded; `pip check` clean; no pytest, mypy, ruff, httpx or pip-tools present. |
| 3b | Clean install, development lock | PASS | Same command succeeded; `pip check` clean. |
| 3c | Regeneration | PASS (Windows, 3.12.10) | `pip-compile` commands from each lock header reproduce both lock bodies byte-for-byte (compared with carriage returns stripped because the checkout used `core.autocrlf=true`). |
| 4 | Negative test, pip | PASS | Flipping both hashes of fastapi in a scratch lock made pip refuse ("THESE PACKAGES DO NOT MATCH THE HASHES") and install nothing; an unpinned requirement is rejected under `--require-hashes`. |
| 4b | Negative tests, `validate_toolchain.py` on scratch copies | PASS | Each made it fail: hash flip; `fastapi>=`; mutated digest; tag-only image without digest; `.python-version` 3.12.14; toolchain Python mismatch; pytest moved into runtime dependencies; pytest block injected into the runtime lock; an API-key-shaped value in `.env.example`; a second secret-shaped value in `.env.example`. |
| 4c | One of two hashes dropped from a lock entry | PASS | Failed on the lock content digest. |
| 5 | Container digest | PASS | Docker Hub registry returned `Docker-Content-Digest: sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258` for `library/python:3.12.15-slim-bookworm`; the body is an OCI image index with 10 entries and its sha256 equals that digest; the same digest-pinned tag appears in `toolchain.toml` and `validate_toolchain.py`. |
| 5b | No Dockerfile or compose | PASS | 20 tracked files, all mode 100644, no Dockerfile, compose file or binary. |
| 6 | Configuration safety (TEST-27 / SEC-07, example-configuration half) | PASS | `.env.example` has six variables matching the Specs ABM_* table, with sample values only; a regex scan of the TASK-02 diffs found no key, token, credential or internal URL; `.gitignore` excludes `.env`, `.env.*`, key files, databases, logs, `.venv` and caches. The baseline claims no required secret. |
| 7 | NFR-09 | PASS | `pip install` appears only in `toolchain.toml` build/setup commands; no network or subprocess code; `dependencies.md` states service startup must not invoke a package manager. |
| 8 | Repository safety | PASS | No placeholder markers, caches, databases or binaries; `validate_governance.py` passes. |
| 9 | Validators | PASS | Both validators pass (14 runtime, 35 development packages). Fault injection on a scratch copy: the governance validator rejects an AWS-key-shaped value in `.env.example` and a stray binary file. |
| 10 | Documentation consistency | PASS | README, CHANGELOG, `dependencies.md` and `TASK-02.md` match the files and Specs scope; no authority expansion. |

## Findings

- **F1, Minor.** CI runs only `scripts/validate_governance.py` on `ubuntu-latest` and does not use a pinned Python. A change to a lock or pin passes CI while `validate_toolchain.py` would fail. Expected, because CI expansion is outside `TASK-02`.
- **F2, Minor.** `validate_toolchain.py` compares against hard-coded expectations and a whole-file digest of each lock; it does not cross-check locks against `pyproject.toml` directly. Every legitimate update needs coordinated edits.
- **F3, Minor.** `validate_governance.py` skips `.venv` and cache directories in its secret scan. A secret-shaped string placed in `.venv` was not flagged. Those paths are git-ignored, so exposure is low, but a force-added file would escape the scan.
- **F4, Observation.** The development lock was generated on Windows (`colorama==0.4.6` is unconditional); Linux regeneration was not tested.
- **F5, Observation.** `.gitignore` omits `venv/` and `env/`.
- **F6, Observation.** No Dockerfile or image build exists, as scoped; the tag-to-patch match relies on the official tag name.
- **F7, Observation.** The work item requires exact-head CI and independent review before merge; the Tester did not inspect the original PR's CI run.

## Requirement trace

- SEC-11 / Gate 4: checks 1, 4b, 5 (pins and digest); 2, 3 (locks and PyPI); pinned tool versions; check 7 (no runtime installs). The secret-scan and static-analysis gate execution are outside this task.
- NFR-09: check 7.
- TEST-27: the example-configuration half is verified by checks 4b and 6. The required-secret-startup half cannot be tested because no application code exists and the baseline declares no required secret.

## Not performed

Execution on exactly Python 3.12.15; container build or run; review of the PR's CI result; Linux lock regeneration.

## Tester's stated next action

Treat `TASK-02` as verified, carry F1 to F3 forward, and when CI or the Dockerfile is next touched add `validate_toolchain.py` to CI, pin Python 3.12.15 there, and confirm Linux regeneration is identical.
