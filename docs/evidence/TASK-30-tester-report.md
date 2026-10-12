# TASK-30 Tester report (re-pass on merged revision)

**Task:** TASK-30 minimal AWS CloudFormation reference (NFR-11, TEST-34, DEC-0006). **Merged commit:** 198ad1b (PR #121). **PR head:** b59ac0c. **Prior re-pass:** ff51d6b (PR #120). **Date:** 2026-10-11. **Role:** fresh-context Tester.

## Gates on 198ad1b

| Gate | Result |
|---|---|
| pytest | `1019 passed, 1 warning in 193.34s` |
| ruff check . | passed |
| ruff format --check . | 174 files already formatted |
| mypy src harness tests scripts | exit 0 |
| validate_governance.py | exit 0 |
| validate_toolchain.py | exit 0 |
| validate_aws_reference.py | AWS REFERENCE VALID (8 resources) |
| test_aws_reference.py, three runs | 20 passed each run |
| `git diff --stat e6cbe81 198ad1b -- src/` | empty |

## Finding resolution

| ID | Prior | Now |
|---|---|---|
| F-3 broken-copy cases missing for the three fixes | Major | Closed: four broken-copy cases; each mutant fails a test |
| F-5 UpdateReplacePolicy not enforced | Minor | Closed: validator checks Retain on the volume |

## Adversarial copies

| Copy | Result |
|---|---|
| UpdateReplacePolicy removed | INVALID (retained on stack deletion and replacement) |
| IngressCidr Default added | INVALID (must not have a default) |
| Single-instance wording removed | INVALID (single-instance limits) |

## Mutants

| Mutant | Result |
|---|---|
| (a) DeletionPolicy and UpdateReplacePolicy check dropped | killed |
| (b) IngressCidr default check dropped | killed |
| (c) single-instance description check dropped | killed |

## Findings

| ID | Class | Status |
|---|---|---|
| N-1 | Note | StarletteDeprecationWarning in the container entry test (httpx with the Starlette client); not related to TASK-30 |

## Verdict

**PASS.** No Blocker or Major findings remain.

## Not verified

- No live deployment.
- No cfn-lint or CloudFormation schema validation; the validator is a reduced static check (a recorded limit).
- Specs main was not re-checked by this Tester.
