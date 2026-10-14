# ABM Service Code

Implementation repository for SuperCool Finances' Account Balances Management Service (ABM).

ABM is a runnable local HTTP service for a **synthetic-data demonstration**. It is designed to run on one Windows computer with Docker Desktop. It is not a production banking service and must not be used with real money or real customer data.

## What ABM does

Within its local demonstration boundary, ABM can:

- register accounts and maintain their lifecycle state;
- return current balances, account status, and transaction history;
- record incoming and outgoing ACH lifecycle events, including settlement, return, rejection, and cancellation;
- perform internal transfers between eligible accounts;
- manage card authorization, clearing, reversal, expiry, late clearing, and refund events;
- apply approved corrections and outgoing-payment restrictions;
- close eligible accounts while retaining required history;
- provide reconciliation reads, health checks, and structured operational logs.

ABM validates the role and account scope supplied by a **trusted caller boundary**. It does not authenticate people, provide a public login, connect to live payment partners, or send real payments.

## Start here

| If you need to… | Read this |
|---|---|
| Run ABM locally on Windows | [Windows local runbook](docs/handover/local-windows-runbook.md) |
| Confirm the handover version, evidence, conditions, and limits | [Handover record](docs/handover/HANDOVER.md) |
| Call the API | Request the matching OpenAPI contract from the service owner; it is governed in the private Specs repository and is not stored in this Code repository. |
| Report a suspected security or data exposure | [Security policy](SECURITY.md) |
| Review recent repository changes | [Changelog](CHANGELOG.md) |
| Contribute to or review implementation work | [Repository policy](docs/governance/repository-policy.md) |

For a local run, use the Windows runbook as the operational source of truth. It covers prerequisites, build, start, readiness, logs, restart, reset, configuration, API examples, and troubleshooting.

## Authority and version

- Approved Specs release: `v1.9.18`
- Exact Specs commit: `507719611c79425fdcfd63d0f5897aed66655db7`
- Specs repository: <https://github.com/juandcn9/ABM-Service-Specs> (private)
- Delivery target: verified local demonstration with synthetic data; not real-money production readiness.

[`SPEC_VERSION`](SPEC_VERSION) is the machine-checked pointer to the governing Specs release. The Code tag or commit named in the handover record identifies the exact delivered version.

## Repository layout

| Location | Purpose |
|---|---|
| `src/abm/` | ABM service implementation |
| `migrations/` | Immutable SQLite schema migration history |
| `tests/` | Automated verification using synthetic data |
| `harness/` | Controlled test and demonstration support code |
| `scripts/` | Development and verification utilities |
| `docs/handover/` | Requestor runbook and handover status record |
| `docs/governance/` | Repository, review, dependency, and deviation rules |
| `docs/work-items/` | Scope, trace, and completion record for each TASK |
| `docs/evidence/` | Sanitized independent Tester reports and supporting evidence |
| `deploy/` | Non-deployed infrastructure reference material |
| `.github/` | Pull-request template, work-item template, and CI configuration |

## Documentation guide

The repository separates requestor guidance from development and audit records.

- **Run and operate the service:** [Windows local runbook](docs/handover/local-windows-runbook.md)
- **See handover status and exact evidence:** [Handover record](docs/handover/HANDOVER.md)
- **Understand security reporting and prohibited data:** [Security policy](SECURITY.md)
- **See delivered changes:** [Changelog](CHANGELOG.md)
- **Understand contribution, review, and merge controls:** [Repository policy](docs/governance/repository-policy.md)
- **See pinned dependencies, image, and installation controls:** [Dependency policy](docs/governance/dependencies.md)
- **Trace a delivery task:** `docs/work-items/`
- **Review independent verification evidence:** `docs/evidence/`

The detailed task and evidence records are retained for traceability. A requestor does not need to read them to start the service.

## Local runtime and security boundary

The supported local route is Docker Desktop on Windows. The service container:

- runs as a non-root user;
- has a read-only application layer;
- stores persistent SQLite data only in one writable Docker volume;
- is documented to bind only to `127.0.0.1`, so it is reachable from the local computer rather than the network; and
- performs readiness checks before reporting that it is ready.

ABM expects caller identity, role, correlation, and where needed account-scope information in trusted caller-context headers. Those headers are valid only behind a controlled local harness or trusted ingress.

> **Do not expose ABM directly to untrusted callers or the public internet.** The service validates trusted caller context; it does not independently authenticate a person or an arbitrary calling application.

The image build and runtime checks are available to developers:

- `python scripts/check_container.py` checks build, non-root execution, read-only application layer, writable data volume, readiness, restart, and manifest information.
- `python scripts/smoke_container.py` performs a black-box HTTP smoke check against a running image.

These scripts are verification tools. The requestor-facing instructions are in the Windows runbook.

## Recovery and data handling

The only supported demonstration recovery is restarting the **same application version** against the intact mounted SQLite volume. On restart, ABM runs its readiness integrity checks before it reports ready.

The local data volume survives a normal stop, start, or replacement of the container. Deleting the volume permanently deletes its local data and is a reset, not a recovery procedure.

ABM makes no claim of backup, restore, disaster recovery, RPO, or RTO. The Windows runbook explains the supported stop, restart, and reset operations.

## AWS reference

[`deploy/aws/abm-reference.json`](deploy/aws/abm-reference.json) is an architectural reference only. It models one private single-container host, encrypted persistent storage, restricted ingress, least-privilege access, centralized logs, and a basic alarm. It is statically validated and is not deployed by this repository.

Validate it with:

```sh
python scripts/validate_aws_reference.py
```

## Current scope

TASK-01 through TASK-30, TASK-36, TASK-37, and TASK-38 record the implemented local-service capability and handover materials. The formal demonstration-release sequence, TASK-31 through TASK-35, is separate and not complete. Work-item and independent Tester records remain available under `docs/work-items/` and `docs/evidence/`.

## For contributors

Implement one dependency-ready Specs TASK at a time. The governing Specs release, task trace, review evidence, dependency controls, and merge requirements are defined in the repository policy and the approved Specs.

Ponytail is development governance tooling for applicable Claude Code work. It is not a runtime dependency, a source of requirements, or a substitute for independent review and testing. See [repository policy](docs/governance/repository-policy.md) and [deviations](docs/governance/deviations.md).

## Limits and non-claims

This repository contains a runnable local HTTP service and container reference for synthetic demonstration data only. It makes no claim of:

- production readiness, regulatory approval, or permission to process real money or real customer data;
- public internet access, production identity, or direct untrusted access;
- live partner or bank integration;
- capacity, availability, horizontal scaling, or load-balanced multi-instance operation;
- backup restoration, disaster recovery, RPO, or RTO.
