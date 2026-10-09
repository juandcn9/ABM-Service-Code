# ABM Service Code

Implementation repository for SuperCool Finances' Account Balances Management Service (ABM).

## Authority

- Approved Specs release: `v1.0.1`
- Exact Specs commit: `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- Specs repository: <https://github.com/juandcn9/ABM-Service-Specs>
- Delivery target: verified local demonstration with synthetic data; not real-money production readiness.

[`SPEC_VERSION`](SPEC_VERSION) is the machine-checked pointer. Every work item and pull request must cite the same immutable Specs release and exact commit.

## Current scope

`TASK-01` establishes repository governance, templates, validation, and the approved Specs pointer. It intentionally contains no service implementation, dependency/toolchain selection, database schema, API route, container, cloud resource, credential, or real customer data.

## Repository map

- [`docs/governance/repository-policy.md`](docs/governance/repository-policy.md): branch, review, evidence, and merge rules.
- [`docs/work-items/TASK-01.md`](docs/work-items/TASK-01.md): active work-item contract and trace.
- [`.github/pull_request_template.md`](.github/pull_request_template.md): required Code PR evidence.
- [`.github/ISSUE_TEMPLATE/work-item.md`](.github/ISSUE_TEMPLATE/work-item.md): future TASK intake.
- [`scripts/validate_governance.py`](scripts/validate_governance.py): dependency-free governance and repository-safety validation.

## Working rule

Implement only one dependency-ready Specs TASK at a time. A normative ambiguity or proposed change to money, customer rights, public behavior, ownership, retention, security, architecture, or governance stops affected work and returns to the Specs change process.

Ponytail is not applicable to this Codex-authored task. Any future Claude Code task must follow the exact Ponytail `v4.13.0` governance in the approved Specs; tool output is never authority.

## Non-claims

This repository does not yet contain a runnable service. It makes no claim of production readiness, regulatory approval, live partner integration, capacity, availability, backup restoration, disaster recovery, or permission to process real money or real customer data.
