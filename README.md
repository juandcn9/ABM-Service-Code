# ABM Service Code

Implementation repository for SuperCool Finances' Account Balances Management Service (ABM).

## Authority

- Approved Specs release: `v1.8.2`
- Exact Specs commit: `3514ccb08ddc8f892e026d4c982b50c43af09736`
- Specs repository: <https://github.com/juandcn9/ABM-Service-Specs>
- Delivery target: verified local demonstration with synthetic data; not real-money production readiness.

[`SPEC_VERSION`](SPEC_VERSION) is the machine-checked pointer. Every work item and pull request must cite the same immutable Specs release and exact commit.

## Current scope

`TASK-01` established repository governance and the approved Specs pointer. `TASK-02` pins the reproducible Python, dependency, lock-generation, safe example-configuration, and future container-base inputs. `TASK-03` adds the empty modular-monolith package layout and import-boundary tests. `TASK-04` makes governance, toolchain, lint, format, type, and test checks required CI gates. `TASK-06` adds the immutable SQLite migrations and runner. `TASK-05` records the Ponytail configuration work item (Blocked on the pin decision). `TASK-08` adds the pure domain value objects, typed results, idempotency fingerprint, and clock port. `TASK-09` adds trusted caller-context parsing, the role and account-scope authorization matrix, and strict transport validation. `TASK-02`, `TASK-03`, `TASK-04`, `TASK-08`, and `TASK-09` have independent Tester records under `docs/evidence/`. The repository intentionally contains no service implementation, API route, built container, cloud resource, credential, or real customer data.

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
- [`src/abm/`](src/abm), [`harness/`](harness), [`tests/`](tests): target layout; [`tests/unit/test_import_boundaries.py`](tests/unit/test_import_boundaries.py) enforces dependency rules.
- [`toolchain.toml`](toolchain.toml): exact Python, lock generator, container digest, and install commands.
- [`.github/pull_request_template.md`](.github/pull_request_template.md): required Code PR evidence.
- [`.github/ISSUE_TEMPLATE/work-item.md`](.github/ISSUE_TEMPLATE/work-item.md): future TASK intake.
- [`scripts/validate_governance.py`](scripts/validate_governance.py): dependency-free governance and repository-safety validation.
- [`scripts/validate_toolchain.py`](scripts/validate_toolchain.py): dependency-free verification of pins, locks, container digest, and safe example configuration.

## Working rule

Implement only one dependency-ready Specs TASK at a time. A normative ambiguity or proposed change to money, customer rights, public behavior, ownership, retention, security, architecture, or governance stops affected work and returns to the Specs change process.

Ponytail was not applicable to the original Codex-authored tasks. Claude Code tasks follow the Ponytail governance in the approved Specs and record `ponytail-review` evidence in the pull request; the version in use and any deviation are recorded in `docs/governance/deviations.md`. Tool output is never authority.

## Non-claims

This repository does not yet contain a runnable service or built image. It makes no claim of production readiness, regulatory approval, live partner integration, capacity, availability, backup restoration, disaster recovery, or permission to process real money or real customer data.
