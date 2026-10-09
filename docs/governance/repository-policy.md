# Repository policy

## Authority and scope

The immutable ABM Service Specs `v1.0.1` commit `5d1cd410399a6fb0154a0117728c409cc7f2ec91` governs this repository. Code, tests, issues, pull-request text, agent output, and tool suggestions cannot redefine the Specs.

## Branch and commit policy

- `main` is the accepted Code record.
- Substantive work uses `task-NN-short-purpose` branches created from current `main`.
- Direct substantive changes to `main`, force pushes, history rewriting, and branch deletion that loses unmerged evidence are prohibited.
- Commits are coherent, reviewable, and identify intent without secrets or private evidence.
- Generated files are committed only when required and reproducible.

## Pull-request gate

Every change uses a pull request containing the approved Specs version/SHA, TASK and trace identifiers, scope and exclusions, checks, security/data assessment, explicit non-claims, and independent-review outcome. Merge requires:

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

Development identities receive only the repository, branch, environment, and service permissions the active TASK needs. No production credentials, real customer data, administrator role, or production or staging mutation is permitted in this demonstration program. Temporary resources use fictitious data and a bounded cleanup record. If a secret may have been exposed, follow [`SECURITY.md`](../../SECURITY.md): stop the affected work, do not repeat the value, report only the locations and secret type, and wait for revocation, rotation, and history cleanup; deleting the visible value is not remediation.

## Findings and severity

- **Blocker:** can corrupt money or state, violate protected authority, expose prohibited data, or make evidence untrustworthy.
- **Major:** required behavior, control, or evidence is missing or materially inconsistent.
- **Minor:** localized defect with a safe workaround and no control weakening.
- **Observation:** non-blocking improvement.

Every Blocker and Major is resolved and reverified before merge, and a phase closes with zero known implementation bugs. Severity may not be downgraded to keep work moving, and a passing automated check never creates a risk acceptance: only an explicit JDC decision does. Security findings are classified as (1) an exploitable or control-bypass defect, which is a Blocker; (2) a known limitation that changes accepted risk, which is Blocked pending explicit JDC acceptance; or (3) deployment hardening outside the demonstration boundary, which is recorded as future work with a production non-claim.

## Lifecycle status values

Every status field in this repository uses exactly one of these values:

| Status | Meaning |
|---|---|
| Draft | Work is incomplete or still under author or reviewer change. |
| Blocked | Work cannot safely proceed until the stated dependency or decision is resolved; the record names the blocker and the next authorized action. |
| Ready for JDC review | Validation and independent review have passed; the exact commit awaits JDC review or authorization. |
| Approved | JDC has approved the named exact commit; the applicable merge or implementation step may still be pending. |
| Implemented | The approved change exists in Code with implementation evidence; independent verification may remain. |
| Verified | Required independent tests and gates passed against the named immutable revision. |

Descriptive classifications such as "out of scope" or "not applicable" belong in a separate note, never in the status field.

## Approval and merge authority

JDC approves and merges. The author of a change never approves it, and self-approval is prohibited. Because this repository has a single maintainer account and platform branch protection is unavailable on the current plan, the rule is procedural: a pull request is merged only when its description records independent fresh-context review evidence for the exact head commit, both required checks are green on that commit, and no Blocker or Major finding is open. A change to a pull-request head after approval invalidates that approval. Force-push after approval, history rewriting, and merging with an unresolved Blocker or Major finding are prohibited, and emergency language does not bypass money, security, or evidence gates.

## Tool applicability

This `TASK-01` implementation is performed by Codex, so Ponytail is recorded as not applicable to this runtime. Claude Code work must use the exact Ponytail version, source, mode, and review commands governed by the approved Specs.

For Claude Code work, Builder Audit runs `ponytail-review` on every implementation diff, `ponytail-debt` whenever `shortcut:` or `ponytail:` markers exist, and `ponytail-audit` at each phase boundary and release candidate; `full` mode is the default. Plugin output is finding input only, never authority, an approver, or a substitute for tests and independent review. While deviation DV-01 in `docs/governance/deviations.md` stands, these commands run with the installed plugin rather than the Specs-pinned `v4.13.0`, every PR says so, and `TASK-05` stays Blocked until the pin is verified or the Specs record an approved change.
