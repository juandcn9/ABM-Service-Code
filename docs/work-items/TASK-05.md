# Work item: TASK-05 — Ponytail configuration and review wiring

**Status:** Blocked

Blocker: the Specs require the exact Ponytail `v4.13.0` source, tag, and commit (`development-workflow.md` section 4), and JDC decided on 2026-10-09 to use the installed plugin 5.1.0 instead (deviation DV-01). The pin cannot be configured or verified without either installing `v4.13.0`, which is a global plugin installation needing explicit approval for the exact action, or an approved Specs upgrade (a dedicated Specs PR with manifest/hook diff and JDC approval of the exact Specs SHA). Next authorized action: JDC chooses one of the options under Decision.

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-05`; `RISK-0005`; Gate 8
- Decision, gap, or risk records: `RISK-0005` (Draft in the Specs, unchanged); DV-01 in `docs/governance/deviations.md`
- Owner role: Builder Auditor (Claude Code)

## Scope

- Objective: configure the exact Ponytail version for Claude Code, verify its manifest and hooks, require `full` mode, and wire `ponytail-review` into each Builder Audit, `ponytail-audit` into phase/release gates, and `ponytail-debt` when shortcut markers exist. Requirements stay in the Specs.
- Included now (no installation, no authority change): this work item; a read-only record of the installed plugin; the review-command wiring in `docs/governance/repository-policy.md`.
- Explicit exclusions: installing or replacing any plugin; changing the Specs; claiming the pin is verified; machine enforcement of the workflow structure (see `TASK-04` exclusions).
- Dependencies and entry gate: `TASK-01` merged.

## Read-only record of the installed plugin (2026-10-09, not a pin verification)

- Location: the Claude Code plugin cache, plugin `ponytail`, directory version `5.1.0`; manifest `plugin.json` reports version `5.1.0`, author Dietrich Gebert.
- Manifest hook file: `hooks/claude-codex-hooks.json` registers three Node.js command hooks: `SessionStart` (`ponytail-activate.js`), `SubagentStart` (`ponytail-subagent.js`), and `UserPromptSubmit` (`ponytail-mode-tracker.js`), each with a 5 second timeout.
- A search of the hook scripts for network access, `fetch`, and process spawning found only `ponytail-map.js` running `git ls-files` with a 3 second timeout; no network calls were found. This is a keyword search, not a full code review, and it covers 5.1.0 only.
- Source tag and commit could not be established: the cached directory is not a git checkout, and no commit hash was recorded. The installed plugin therefore is not shown to match any tagged upstream release.

## Decision (JDC)

Options to close this task and `RISK-0005`:

1. Keep DV-01 and adopt 5.1.0 formally: the Updater role prepares a Specs upgrade PR (proposed exact version and commit, release notes, manifest/hook diff, compatibility and security assessment, validator and document updates) for JDC exact-SHA approval. Slowest, but removes the deviation and keeps the Specs the single authority.
2. Follow the Specs: install `v4.13.0` from the authorized repository at the pinned commit, with the exact installation action approved by JDC, then verify the manifest and hooks. Meets the Specs now, but changes JDC's chosen tooling and needs a global plugin installation.
3. Keep DV-01 indefinitely as a declared deviation. Cheapest; leaves Gate 8 evidence from an unpinned tool and this task Blocked.

Recommendation: option 1.

## Acceptance evidence

- Focused tests: not applicable; documentation and governance only.
- Required broader gates: `validate-governance` and `quality-gates` on the PR head.
- Failure, concurrency, authorization, and recovery cases: not applicable.
- Documentation/trace updates: `docs/governance/repository-policy.md` review wiring; README and CHANGELOG.

## Implementation notes

- Until this task is unblocked, every Claude Code task records `ponytail-review` (and `ponytail-debt` when markers exist, and `ponytail-audit` at phase/release boundaries) as run with the installed plugin and cites DV-01. Plugin output is finding input, never authority.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: pending.
- Review findings/resolution: pending.
- Residual risks: Gate 8 Ponytail evidence comes from an unpinned tool until a decision is implemented.
- Next safe action: JDC decision on the options above.
