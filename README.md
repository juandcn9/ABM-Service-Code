# ABM Service Code

Implementation repository for SuperCool Finances' Account Balances Management Service (ABM).

## Authority

- Approved Specs release: `v1.9.12`
- Exact Specs commit: `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f`
- Specs repository: <https://github.com/juandcn9/ABM-Service-Specs>
- Delivery target: verified local demonstration with synthetic data; not real-money production readiness.

[`SPEC_VERSION`](SPEC_VERSION) is the machine-checked pointer. Every work item and pull request must cite the same immutable Specs release and exact commit.

## Current scope

TASK-01 through TASK-22 establish the governed toolchain, modular-monolith boundaries, SQLite schema and transaction model, monetary domain, application commands and reads, readiness, lifecycle rules, corrections, restrictions, closure, and retention controls. TASK-23 supplies the application/persistence security-negative evidence defined by DEC-0051. HTTP, observability, container, infrastructure, and release evidence remain later tasks. Work-item and independent Tester records are under `docs/work-items/` and `docs/evidence/`. The repository uses only synthetic demonstration data and contains no API route, built container, cloud resource, credential, or real customer data.

## Repository map

- [`docs/governance/repository-policy.md`](docs/governance/repository-policy.md): branch, review, evidence, and merge rules.
- [`docs/governance/dependencies.md`](docs/governance/dependencies.md): exact dependency, image, installation, and update controls.
- [`docs/work-items/TASK-01.md`](docs/work-items/TASK-01.md): repository-governance work item and trace.
- [`docs/work-items/TASK-02.md`](docs/work-items/TASK-02.md): reproducible-toolchain work item and evidence contract.
- [`docs/work-items/TASK-03.md`](docs/work-items/TASK-03.md): package-layout and import-boundary work item.
- [`docs/work-items/TASK-04.md`](docs/work-items/TASK-04.md): CI quality-gate work item.
- [`docs/work-items/TASK-06.md`](docs/work-items/TASK-06.md): migrations work item; [`migrations/`](migrations) holds the immutable schema migrations.
- [`docs/work-items/TASK-07.md`](docs/work-items/TASK-07.md): SQLite connection and transaction-unit work item.
- [`docs/work-items/TASK-08.md`](docs/work-items/TASK-08.md): domain value objects, results, fingerprint, and clock port work item.
- [`docs/work-items/TASK-09.md`](docs/work-items/TASK-09.md): caller context, authorization, and transport validation work item.
- [`docs/work-items/TASK-05.md`](docs/work-items/TASK-05.md): Ponytail configuration work item (Blocked on the pin decision).
- [`docs/work-items/TASK-10.md`](docs/work-items/TASK-10.md): idempotency foundation and registration work item.
- [`docs/work-items/TASK-12.md`](docs/work-items/TASK-12.md): startup and readiness work item.
- [`docs/work-items/TASK-23.md`](docs/work-items/TASK-23.md): application/persistence security-negative evidence and exact later-facet ownership.
- [`src/abm/`](src/abm), [`harness/`](harness), [`tests/`](tests): target layout; [`tests/unit/test_import_boundaries.py`](tests/unit/test_import_boundaries.py) enforces dependency rules.
- [`toolchain.toml`](toolchain.toml): exact Python, lock generator, container digest, and install commands.
- [`.github/pull_request_template.md`](.github/pull_request_template.md): required Code PR evidence.
- [`.github/ISSUE_TEMPLATE/work-item.md`](.github/ISSUE_TEMPLATE/work-item.md): future TASK intake.
- [`scripts/validate_governance.py`](scripts/validate_governance.py): dependency-free governance and repository-safety validation.
- [`scripts/validate_toolchain.py`](scripts/validate_toolchain.py): dependency-free verification of pins, locks, container digest, and safe example configuration.

## Container demonstration (TASK-27)

The service image is non-root, has a read-only application layer, and writes only to one data volume. The container check runs in CI, on a runner with a container engine (the development workstation has none, so it is not verified locally).

```sh
docker build -t abm:local .
docker volume create abm-data
docker run -d --name abm --read-only   -v abm-data:/data   -e ABM_MODE=demonstration -e ABM_TRUSTED_INGRESS=true -e ABM_CLOCK_MODE=system   -p 127.0.0.1:8000:8000 abm:local
curl -s http://127.0.0.1:8000/health/ready
```

`ABM_TRUSTED_INGRESS=true` is set only where the caller-context boundary is controlled (SEC-01). The container refuses `ABM_CLOCK_MODE=controlled`. Run `python scripts/check_container.py` to repeat the checks (build, non-root, read-only, restart, manifest).

## Working rule

Implement only one dependency-ready Specs TASK at a time. A normative ambiguity or proposed change to money, customer rights, public behavior, ownership, retention, security, architecture, or governance stops affected work and returns to the Specs change process.

Ponytail was not applicable to the original Codex-authored tasks. Claude Code tasks follow the Ponytail governance in the approved Specs and record `ponytail-review` evidence in the pull request; the version in use and any deviation are recorded in `docs/governance/deviations.md`. Tool output is never authority.

## Non-claims

This repository does not yet contain a runnable HTTP service or built image. It makes no claim of production readiness, regulatory approval, live partner integration, capacity, availability, backup restoration, disaster recovery, or permission to process real money or real customer data.
