# Repository policy

## Authority and scope

The immutable ABM Service Specs `v1.9.4` commit `f4f4f2061739c5b2a20c0e4715f2caeecd3bb2b4` governs this repository. Code, tests, issues, pull-request text, agent output, and tool suggestions cannot redefine the Specs.

## Branch and commit policy

- `main` is the accepted Code record.
- Substantive work uses short-lived `task-NN-short-purpose` branches created from current `main`; documentation-only and corrective changes use `docs/short-purpose` branches.
- Direct substantive changes to `main`, force pushes, history rewriting, and branch deletion that loses unmerged evidence are prohibited.
- Commits are coherent, reviewable, and identify intent without secrets or private evidence. Credentials, real customer data, local databases, caches, and unreviewed binaries are never committed.
- Generated files are committed only when required and reproducible.

## Pull-request gate

Every change uses a pull request containing the approved Specs version/SHA, TASK and trace identifiers, the behavior and boundaries changed, scope and exclusions, focused and regression checks, migrations, compatibility, and rollback or recovery impact, security/data assessment, risks, gaps, and decisions, explicit non-claims, and independent-review outcome. Merge requires:

1. the exact branch revision under review;
2. all required checks green;
3. no unresolved Blocker or Major finding;
4. complete requirement-to-evidence trace;
5. no secret, prohibited data, uncontrolled placeholder, or unsupported claim;
6. confirmation that merge will not alter the approved revision.

The target repository controls are: pull requests for `main`, required `validate-governance` and `quality-gates` statuses (neither is advisory; a failing or skipped required check blocks merge), resolved review conversations, no force push, and no deletion. Where hosting cannot enforce a control, the same rule remains mandatory procedure and the PR records its evidence. GitHub branch protection and required status checks are unavailable for this private repository on the current plan (the API returns 403), so these controls are procedural: a merge is permitted only when the PR shows the required checks green on the exact head SHA, with the evidence recorded in the PR.

## Review independence

The author cannot provide the sole independent verification. A fresh-context reviewer receives the approved Specs SHA, Code diff, evidence, and declared risks; it checks omissions, authority expansion, security/data exposure, unnecessary complexity, and reproducibility. The reviewer does not repair the implementation during that verification pass.

## Task and evidence discipline

- Activate only a dependency-ready TASK.
- Use the work-item and pull-request templates.
- Keep evidence reproducible, sanitized, and attributable to exact revisions.
- Do not skip or relabel a failing required check.
- Record failures that affect confidence; never hide them by rerunning only the passing path.
- Stop and escalate any normative ambiguity, required approval, security weakening, or risk acceptance.

## Human approval for risky actions

Explicit human approval is required immediately before each of these, and it must name the exact target and action; a general task approval is not enough:

- destructive filesystem or Git operations;
- force-push or history rewrite;
- execution of a destructive migration;
- credential creation, rotation, or revocation;
- global package or plugin installation;
- permission expansion;
- execution of a downloaded or remote script.

Development identities receive only the repository, branch, environment, and service permissions the active TASK needs. No production credentials, real customer data, administrator role, or production or staging mutation is permitted in this demonstration program. Temporary resources use fictitious data and a bounded cleanup record. Use documented placeholders and external secret references only. Secrets are prohibited in source, prompts, issues, pull requests, chat, logs, screenshots, fixtures, generated evidence, copied terminal output, and plugin or tool telemetry. If a secret may have been exposed, follow [`SECURITY.md`](../../SECURITY.md): stop the affected work, do not repeat the value, report only the locations and secret type, preserve sanitized evidence, notify JDC, and wait for revocation, rotation, and history and cache cleanup; deleting the visible value is not remediation.

Before Cursor is permitted for repository changes, the Builder Auditor records that privacy and data-training controls were reviewed and that training and data-retention sharing is disabled to the extent the product permits. Cursor autonomous or background agents, Tab or Composer code application, and equivalent write-capable features stay disabled for this project unless a later exact-SHA Specs decision authorizes them; read-only navigation does not confer write authority.

## Findings and severity

- **Blocker:** can corrupt money or state, violate protected authority, expose prohibited data, or make evidence untrustworthy.
- **Major:** required behavior, control, or evidence is missing or materially inconsistent.
- **Minor:** localized defect with a safe workaround and no control weakening. Minor documentation findings are resolved or explicitly scheduled with no false completeness claim.
- **Observation:** non-blocking improvement.

Every Blocker and Major is resolved and reverified before merge, and a phase closes with zero known implementation bugs. Severity may not be downgraded to keep work moving, and a passing automated check never creates a risk acceptance: only an explicit JDC decision does. Security findings are classified as (1) an exploitable or control-bypass defect, which is a Blocker; (2) a known limitation that changes accepted risk, which is Blocked pending explicit JDC acceptance; or (3) deployment hardening outside the demonstration boundary, which is recorded as future work with a production non-claim.

## Lifecycle status values

Every status field in this repository uses exactly one of these values:

| Status | Meaning |
|---|---|
| Draft | Work is incomplete or still under author or reviewer change. |
| Blocked | Work cannot safely proceed until the stated dependency or decision is resolved; the record names the blocker and the next authorized action. |
| Ready for JDC review | Validation and independent review have passed; the exact commit awaits JDC review or authorization. |
| Approved | JDC has approved the named exact commit; the applicable merge, tag, or implementation step may still be pending. |
| Implemented | The approved change exists in Code with implementation evidence; independent verification may remain. |
| Verified | Required independent tests and gates passed against the named immutable revision. |

Descriptive classifications such as "out of scope" or "not applicable" belong in a separate note, never in the status field.

## Approval and merge authority

JDC approves and merges. The author of a change never approves it, and self-approval is prohibited. Because this repository has a single maintainer account (JDC and the agents act through the one GitHub account that owns it, so the platform cannot show who approved) and platform branch protection is unavailable on the current plan, the rule is procedural and independence is shown by review evidence, not by account identity: a pull request is merged only when its description records independent fresh-context review evidence for the exact head commit, both required checks are green on that commit, and no Blocker or Major finding is open. A change to a pull-request head after approval invalidates that approval. A pull request that changes behavior without updating its tests and trace is incomplete. The CI workflow is pinned by a workflow digest in `scripts/validate_governance.py`: a deliberate workflow change updates the digest in the same commit and is reviewed like any control change, and only the reviewed files under `.github/` are allowed. Force-push after approval, history rewriting, and merging with an unresolved Blocker or Major finding are prohibited, and emergency language does not bypass money, security, or evidence gates.

## Tool applicability

The original `TASK-01` implementation was performed by Codex, so Ponytail was recorded as not applicable to that runtime; follow-up changes made with Claude Code record their `ponytail-review` evidence in the pull request. Claude Code work must use the exact Ponytail version, source, mode, and review commands governed by the approved Specs.

For Claude Code work, Builder Audit runs `ponytail-review` on every implementation diff, `ponytail-debt` whenever `shortcut:` or `ponytail:` markers exist, and `ponytail-audit` at each phase boundary and release candidate; `full` mode is the default. Plugin output is finding input only, never authority, an approver, or a substitute for tests and independent review. Deviation DV-01 is closed (`docs/governance/deviations.md`): the Specs pin Ponytail `v5.1.0` (DEC-0013, DEC-0020), and the installed copy matches the pinned file tree, so `TASK-05` is Implemented and every PR records the verified version.
