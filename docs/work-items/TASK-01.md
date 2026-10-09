# Work item: TASK-01 — establish Code repository governance

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-01`; `BT-06`; `SEC-11`; `TEST-26`; governance controls
- Decision, gap, or risk records: no new decision or gap; existing Specs risks remain unchanged
- Owner roles: Updater + Builder Auditor; Codex is the execution runtime for this implementation, and final verification requires an independent Tester

## Scope

- Objective: create the private Code repository foundation, immutable Specs pointer, repository policy, work/PR templates, and dependency-free governance validation.
- Included files/components: repository documentation, GitHub templates/workflow, ignore policy, security notice, and governance validator.
- Explicit exclusions: Python/dependency pinning, package layout, service behavior, database/API contracts, containers, infrastructure, deployment, credentials, and real data.
- Dependencies and entry gate: Specs handover `v1.0.1` completed; no open normative GAP.

## Acceptance evidence

- Focused tests: `python scripts/validate_governance.py` succeeds from repository root.
- Required broader gates: GitHub `validate-governance` job succeeds at the exact PR head; independent administrative/security review reports no unresolved Blocker or Major.
- Failure, concurrency, authorization, and recovery cases: runtime cases are outside `TASK-01`; validation must fail on a missing/mismatched Specs pointer, missing required file/heading, uncontrolled placeholder, or probable secret pattern.
- Documentation/trace updates: README, `SPEC_VERSION`, repository policy, templates, changelog, and this work item.

## Implementation notes

- No runtime or development dependency is introduced.
- The CI checkout action is pinned to its reviewed commit.
- Ponytail is not applicable to this Codex runtime; future Claude Code work remains governed by the Specs pin and commands.
- Repository controls are documented as mandatory policy; no product or technical architecture decision is added.

## Completion

- Code commit/PR: exact commit and PR are the GitHub review record for branch `task-01-repository-governance`.
- Commands/checks and results: local validator, exact-head CI, and secret/prohibited-data scan are required before merge.
- Review findings/resolution: recorded in the PR; all Blocker/Major findings must be resolved and reverified.
- Residual risks: none introduced by this work item.
- Next safe action: begin `TASK-02` only after this exact `TASK-01` revision is approved and merged.
