# Dependency and toolchain policy

## Authority and scope

`TASK-02` implements `SEC-11`, `NFR-09`, and `TEST-27` from approved Specs `v1.0.1` at `5d1cd410399a6fb0154a0117728c409cc7f2ec91`. It selects only the already-approved Python/FastAPI/Pydantic/SQLite/pytest/OCI toolchain and adds no product behavior.

## Reproducible inputs

- `.python-version` pins the local CPython patch release.
- `toolchain.toml` pins the same Python release, the official multi-platform container manifest by digest, the lock generator, and hash-enforced install commands.
- `pyproject.toml` pins every direct runtime and development dependency exactly.
- `requirements.lock` and `requirements-dev.lock` pin the complete resolved graphs with SHA-256 artifact hashes. The development graph includes the lock generator plus its installer/build dependencies, including normally unsafe bootstrap packages, so regeneration does not depend on ambient unreviewed versions.
- SQLite is provided only by Python's standard library; no SQLite wrapper or database service is added.

Runtime and development dependencies remain separate. The development lock contains the runtime graph and pinned lock-generation graph so that one hash-enforced command creates a complete verification environment; the runtime lock never contains development/build tools.

## Installation boundary

Dependency installation occurs only during an explicit development or image-build step. Service startup and execution must not invoke a package manager or access a package registry. The future container build must use the exact image reference from `toolchain.toml` and install `requirements.lock` with `--require-hashes`.

No package may be installed from a Git URL, branch, local mutable path, remote script, or unverified archive. No optional `standard`/`all` extra is selected implicitly.

## Controlled update procedure

An update uses its own Code PR and must:

1. state the package/image purpose and exact old/new versions or digests;
2. obtain metadata and artifacts only from the official Python, PyPI, or Docker Official Image source;
3. install the generator through the hash-enforced development lock, then regenerate both locks with the pinned generator, Python 3.12, and `--allow-unsafe` for the development bootstrap graph;
4. run hash-enforced clean-environment installs and all then-applicable gates;
5. inspect transitive changes, licenses, advisories, and compatibility;
6. preserve explicit production and recovery non-claims.

Automated update proposals receive the same tests and independent review as authored code. They never merge automatically.

## Safe example configuration

`.env.example` contains only documented non-secret demonstration values. The baseline has no required secret. Real credentials, customer data, host-specific private paths, and production endpoints are prohibited.

## Continuous-integration enforcement

The `quality-gates` CI job installs `requirements-dev.lock` with `--require-hashes --only-binary=:all:` on the exact Python patch in `.python-version`, verifies the interpreter version, and runs `scripts/validate_toolchain.py`, `ruff check`, `ruff format --check`, `mypy` (over `src`, `harness`, `tests`, and `scripts`), and `pytest`. `.gitattributes` forces LF so lock digests do not depend on a contributor's `core.autocrlf`.

## Container image (TASK-27)

The image build is the only installation step: `Dockerfile` installs `requirements.lock` with `--require-hashes` into the digest-pinned base image from `toolchain.toml`. Service startup never invokes a package manager. Nothing else is installed into the image.
