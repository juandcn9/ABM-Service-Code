# TASK-01 independent Tester report (sanitized record)

**Provenance:** final report of a fresh-context Tester agent on 2026-10-09, launched by the Claude Code session that later worked on the program. `TASK-01` was built by a different agent (Codex) in another environment and had no independent verification record. The Builder reformatted the report. Evidence input, not Specs authority.

- Revision tested: Code `a61319842567d859a7b2fd5f68b06690e40e6fd8` (merge of PR #1 onto the initial commit); later state compared: `e3aada8`.
- Specs: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91` (the tag was confirmed to resolve to that commit in the Specs repository).
- Environment: Python 3.12.10 on Windows in a detached worktree and a scratch copy; read-only GitHub CLI.

## Result

PASS with findings: no Blocker, **one Major (F1)**, Minor findings F2 to F4, Observation F5. `TASK-01` may be recorded Verified only after F1 is resolved and re-verified (or explicitly accepted by JDC) and the Minor findings are fixed or scheduled.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| Specs pointer (`SPEC_VERSION`, README, tag resolution) | PASS | Pointer holds repository, `v1.0.1`, and the commit; the tag resolves to the same commit. |
| Pull-request template against the Specs template | PASS with Minor | All sections present; wording drift (F2). |
| Issue template against the work-item template | PASS | Only the title line became front matter. |
| Repository policy against workflow sections 2, 3, 9 and authority sections 5 to 7 | **FAIL (Major F1)** | Present: protected `main`, task branches, no force-push or history rewrite, independent review, no merge with Blocker or Major. Absent: human approval before destructive actions, severity handling, lifecycle status values, self-approval prohibition. |
| `.gitignore` and `SECURITY.md` against workflow section 9 and SEC-06 | PASS | Credentials, keys, databases, logs, caches, `.venv`, and private evidence are ignored; the exposure procedure is documented. |
| Governance validator run | PASS | `TASK-01 VALIDATION PASSED`. |
| Validator mutation tests (33 mutations) | Mixed | Caught: missing file, changed pointer, secrets, binaries, placeholders, a broken template heading, an unpinned action, `contents: write`. Missed: pointer changed only in the policy or work item, policy reduced to bare headings, template fields deleted, workflow checks defeated by comments, `.gitignore` rules deleted or replaced by a comment, card number or email in markdown, NUL byte, invalid status value (F3). |
| CI workflow | PASS | `contents: read`, no `pull_request_target`, expected triggers; the checkout SHA belongs to the claimed tag. |
| Secrets and prohibited-data scan of the tree | PASS | Only policy prose and the validator's own patterns matched. |
| CI result for the commit | PASS | The push run on `a613198` succeeded. |
| Later changes (`a613198..e3aada8`) | PASS | Nothing weakened a TASK-01 control; later work added the `quality-gates` job, widened the file allow-list, scanned tracked files, and stated the branch-protection limit. |

## Findings

- **F1 (Major):** the policy omitted required controls. Failing case: a search of the policy for the words destructive, approval, severity, downgrade, credential, Verified, Draft, or self-approval returned nothing. PR #1 was authored and merged by the same account.
- **F2 (Minor):** the pull-request template drifted from the Specs template (the Ponytail line lacked "`full` mode" and "`ponytail-review`"; "DEC-nnnn/GAP-nnnn/RISK-nnnn" became "DEC/GAP/RISK records"; some fields were reworded). The validator did not detect it.
- **F3 (Minor):** the validator was partly vacuous (see the mutation results above); substring tests satisfied by comments; no payment-card or NUL scan.
- **F4 (Minor):** claims stronger than the evidence: branch protection being unavailable (HTTP 403) was not disclosed at that revision; "residual risks: none"; the Completion section recorded no commit, PR, or results; PR #1 described an independent review but shows no review or comment, so no attributable independent review existed.
- **F5 (Observation):** the `# v5` comment names a moving tag; `persist-credentials` left at its default; `.gitignore` lacked `*.p12`, `*.pfx`, `*.exe`, `*.dll`; `SECURITY.md` does not name its private reporting channel.

## Not verified

Whether the independent review described by PR #1 took place; branch protection itself (HTTP 403); the later validator under the same mutation set (done in the follow-up change below).

## Disposition

F1 to F4 and the `.gitignore` part of F5 are addressed in the follow-up change that carries this report: the policy gains sections on human approval for risky actions, findings and severity, lifecycle status values, and approval and merge authority; the pull-request template matches the Specs fields; the validator now uses anchored checks and a committed mutation guard (`tests/security/test_governance_validator.py`, 79 damaging cases and 8 harmless look-alikes); the work item records the real completion facts. A fresh-context re-verification of that change is required before `TASK-01` is recorded Verified.
