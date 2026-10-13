# Work item: TASK-05 — Ponytail configuration and review wiring

**Status:** Verified

Resolved: the Specs now pin Ponytail `v5.1.0` (DEC-0013, merged with Specs PR #3). The installed copy was verified against the pinned tree; see Verification below. Deviation DV-01 is closed.

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

- Every Claude Code task records `ponytail-review` (and `ponytail-debt` when markers exist, and `ponytail-audit` at phase/release boundaries) as run with the installed plugin and cites DV-01. Plugin output is finding input, never authority.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: the file-tree verification of the installed Ponytail 5.1.0 against tag `v5.1.0` (commit `9cc65d0`) is recorded in PR #18, which closes DV-01.
- Review findings/resolution: no separate review is recorded for PR #18.
- Residual risks: the plugin is installed per machine; a new environment must install 5.1.0 and repeat the file-tree check.
- Next safe action: none for TASK-05. The Code pin is `v1.6.0` (PR #29).

## Verification (2026-10-10)

- Source: `https://github.com/DietrichGebert/ponytail`, tag `v5.1.0` resolves to commit `9cc65d03aa2da1db7121b912d03596409ee340b8` (DEC-0013).
- Installed copy: the plugin cache directory for version `5.1.0`, compared file by file with `git archive` of the pinned commit: 199 files on both sides, all contents identical, no file missing or extra. The only installed extra is `.in_use/31236`, a runtime marker of the plugin, excluded from the comparison.
- Method: read-only. The upstream repository was cloned into a scratch folder and nothing from it was executed.

## Verified record

- Independent Tester PASS on the merged revision `e333cdf` (PR #128, merged as `9757d88`; merged content identical to the tested head): `docs/evidence/TASK-05-remediation-tester-report.md`. Blocker 0, Major 0, Minor 0.
- Earlier findings closed: the DEC-0020 counts (42 byte-for-byte, 157 CRLF-normalized, total 199) in `docs/evidence/TASK-05-ponytail-verification.md` and the stale "Blocked" wording (fixed in `c8360f7` and `e333cdf`).
- The historical options text in the Decision section (`Blocked` as the status of a rejected option) is kept as history.

## Scheduled items

- Tester Observation 3 (`docs/evidence/TASK-05-remediation-tester-report.md`): the evidence header and the README cite DEC-0020, while the Resolved line cites DEC-0013 only. Traceability wording, not a status claim. Owner Builder. Trigger: the next Ponytail doc change.
