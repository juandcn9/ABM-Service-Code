# Work item: TASK-30 — minimal AWS CloudFormation reference with static validation and explicit non-claims

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.12` / `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f` (Code pin). Specs `main` includes TASK-30's row in `specs/09` (Draft).
- TASK and affected IDs: `TASK-30`; `NFR-11` (IaC validates syntactically, declares the single-instance boundary, and makes no backup/restore or production-readiness claim); `TEST-34`; `DEC-0006` (native CloudFormation, validation only); Specs section 11 (AWS reference boundary).
- Dependencies: `TASK-27` (Verified; container image).
- Owner role: Builder (Claude Code); independent Tester verification of the merged head is required.

## Scope

- Objective: a CloudFormation reference that models the single-container host from Specs section 11, with static validation and explicit non-claims. No account is used and nothing is deployed.
- Included:
  1. `deploy/aws/abm-reference.json`: CloudFormation JSON (no third-party YAML parser is in the lock). Resources: one EC2 instance in a private subnet with no public address and an encrypted root volume; an encrypted gp3 data volume attached to it; a security group whose ingress CIDR is a parameter with no default; an instance role with only log-write and parameter-read permissions scoped to a parameter prefix; a log group with retention; a basic status-check alarm bound to the instance. Parameters hold non-secret values and secret references by name only.
  2. `scripts/validate_aws_reference.py` (standard library): checks JSON syntax; the allowed resource types only; exactly one instance; encrypted volumes; no public address; no open ingress; ingress CIDR from a parameter; no wildcard IAM action or resource; log retention; a bound alarm; no secret-like defaults; and the non-claims in the description.
  3. `tests/unit/test_aws_reference.py`: the reference is valid, and each rule has a broken copy that the validator must name.
  4. `deploy/` joins the TEST-32 recovery-claim scan (`tests/unit/test_recovery_claims.py`).
  5. README section for the reference and its non-claims.
- Explicit exclusions:
  - Any live deployment, AWS account, or CloudFormation service call (validation only, DEC-0006).
  - cfn-lint or other third-party validators: not in the lock; the custom validator is a reduced check, recorded as a limit.
  - Databases, autoscaling, load balancing, multi-instance design, backup, restore, disaster recovery, RPO, RTO, live partner integration: all excluded and not claimed.

## Acceptance evidence

- Focused tests: `tests/unit/test_aws_reference.py` (reference valid; 15 broken-copy cases) and the recovery-claim scan pass.
- Required broader gates: full pytest, ruff check and format, mypy, both validators, and CI on the exact PR head.

## Implementation notes

- CloudFormation JSON is the native template format, so no YAML parser is needed.
- Validation is a reduced static check. It covers the TEST-34 rules; it does not replace a full CloudFormation schema check.

## Non-claims

- No deployment, no live AWS account, no cfn-lint or full schema validation.
- No backup, restore, disaster-recovery, RPO, RTO, or production-readiness claim.
- SQLite is the demonstration database; a production AWS design is out of scope.

## Completion

- Code commit/PR: branch `feat/task-30-aws` from `main`; PR not yet opened.
- Commands/checks and results: `tests/unit/test_aws_reference.py` and the recovery-claim scan: 19 passed; the validator reports the reference valid; ruff and mypy pass.
- Review findings/resolution: pending.
- Residual risks: the static validator is a reduced check, not a full CloudFormation schema validation; the template has never been deployed.
- Next safe action: open the Code PR, run CI, then the Tester pass on the merged head.
