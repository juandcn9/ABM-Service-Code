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

- Code commit/PR: PR #1, merge commit `a61319842567d859a7b2fd5f68b06690e40e6fd8` (content commits `a968217` and `dfe323e`).
- Commands/checks and results: `scripts/validate_governance.py` passed locally and in CI (`validate-governance`) on `dfe323e` and on the merge commit, and the tree contains no secret or prohibited data.
- Review findings/resolution: PR #1 shows no attributable independent review: it was authored and merged by the same account, and its text described an independent review that left no record. The first independent verification is the fresh-context Tester pass of 2026-10-09, which found one Major (the repository policy omitted several controls the Specs require), plus Minor findings on template drift, a partly vacuous validator, and claims stronger than the evidence. All are addressed by the follow-up documentation change that carries this text; see Independent verification.
- Residual risks: controls are procedural (platform branch protection is unavailable on this plan); the validator cannot judge the substance of a review; sensitive-data scanning beyond secret patterns and payment-card numbers is not automated.
- Next safe action: re-verification of the follow-up change, then the Verified record.

## Independent verification

- Role and context: Tester, a fresh-context agent that did not build `TASK-01`, 2026-10-09. The sanitized report is committed at [`docs/evidence/TASK-01-tester-report.md`](../evidence/TASK-01-tester-report.md).
- Revision tested: Code `a61319842567d859a7b2fd5f68b06690e40e6fd8`. Specs `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Result: PASS with findings: one Major (the repository policy omitted required controls), three Minor, one Observation. The findings are addressed by the follow-up change that carries this section (policy sections, template alignment, validator hardening with a committed mutation guard, honest completion record).
- Status: stays `Implemented` until a fresh-context re-verification of that change passes; the Verified record is then a separate documentation change.
