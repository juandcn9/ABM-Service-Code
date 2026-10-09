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

The target repository controls are: pull requests for `main`, required `validate-governance` and `quality-gates` statuses (neither is advisory; a failing or skipped required check blocks merge), resolved review conversations, no force push, and no deletion. Where hosting cannot enforce a control, the same rule remains mandatory procedure and the PR records its evidence.

## Review independence

The author cannot provide the sole independent verification. A fresh-context reviewer receives the approved Specs SHA, Code diff, evidence, and declared risks; it checks omissions, authority expansion, security/data exposure, unnecessary complexity, and reproducibility. The reviewer does not repair the implementation during that verification pass.

## Task and evidence discipline

- Activate only a dependency-ready TASK.
- Use the work-item and pull-request templates.
- Keep evidence reproducible, sanitized, and attributable to exact revisions.
- Do not skip or relabel a failing required check.
- Record failures that affect confidence; never hide them by rerunning only the passing path.
- Stop and escalate any normative ambiguity, required approval, security weakening, or risk acceptance.

## Tool applicability

This `TASK-01` implementation is performed by Codex, so Ponytail is recorded as not applicable to this runtime. Claude Code work must use the exact Ponytail version, source, mode, and review commands governed by the approved Specs.
