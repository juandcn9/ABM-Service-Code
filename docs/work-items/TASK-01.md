# Work item: TASK-01 — establish Code repository governance

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.9.17` / `b0633079c8126fc648d1a4beff30f27046f8e88e`
- TASK and affected IDs: `TASK-01`; `BT-06`; `SEC-11`; `TEST-26`; governance controls
- Decision, gap, or risk records: no new decision or gap; existing Specs risks remain unchanged
- Owner roles: Updater + Builder Auditor; Codex was the execution runtime for the original implementation and Claude Code for the follow-up change, and final verification requires an independent Tester

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
- Ponytail was not applicable to the original Codex runtime; the Claude Code follow-up change records its `ponytail-review` evidence in its pull request.
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

## Verified record

- Independent Tester PASS with findings on `fe28fd9` (Blocker 0, Major 0), merged to `main` as `3eb1e69` (PR #130). The merged result was checked: the governance validator and the guard tests pass on the merge with current `main` (220 passed). Report: `docs/evidence/TASK-01-remediation-tester-report.md`.
- Earlier Tester Majors were closed in order: the policy omissions (R1 to R4, then the authority pause triggers and the hook, codebase-map and ID rules), and the TEST-32 recovery guard. The guard keeps its strict disclaimer pattern; the one exception is the Gate 7 row, matched by exact line (see GAP-0004 in Specs).
- Scheduled items, with owners and triggers: the policy phrase checks are whole-document substring checks (Tester Observation O1; owner Builder; trigger the next change to `scripts/validate_governance.py`). Non-blocking observations from the earlier Tester (persist-credentials default, SECURITY.md private channel) stay as recorded in the Tester reports; owner Builder; trigger the next governance change.
- Scheduled item (remediation Observation 1, `docs/evidence/TASK-01-remediation-tester-report.md`): `scripts/validate_governance.py` passes an appended Gate 7 claim, so only the pytest guard catches it. Owner Builder. Trigger: the next change to `scripts/validate_governance.py`.
