# TASK-04 independent Tester report (sanitized record)

**Provenance:** final reports of two fresh-context reviewer/Tester agents on 2026-10-09 (first review of PR #5 head `44830ab`, then a Tester pass on head `870ddb3`), launched by the Claude Code session that built `TASK-04`. The Builder reformatted them. Evidence input, not Specs authority.

- Revision verified: Code PR #5 head `870ddb31e9dd6a5820c33f5914f4357c98194576`. The merged head `cc5e93a28a76b15e6905e3ed564d6c53b598f27a` (merge commit `4dacac2`) differs only by documentation wording that responds to this review (stale work-item text and the SQL-scan limits); CI passed on it.
- Specs: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Environment: Python 3.12.10 on Windows, throwaway virtual environments from `requirements-dev.lock` (`--require-hashes --only-binary=:all:`). CI evidence on Linux with CPython 3.12.15.

## Result

PASS with findings. Zero Blocker, zero Major.

## Checks

| Check | Result | Evidence summary |
|---|---|---|
| `pytest`, `ruff check`, `ruff format --check`, `mypy src harness tests scripts`, both validators | PASS | 9 tests passed; 27 files formatted; mypy clean on 13 files. |
| CI at the head | PASS | `validate-governance` and `quality-gates` green on push and pull-request runs; log shows `Successfully set up CPython (3.12.15)`, the exact-patch assertion passing, hash-verified install, and all steps. |
| Workflow security | PASS | Actions pinned by full SHA and verified against tags (`actions/checkout` v5, `actions/setup-python` v6.0.0); `permissions: contents: read`; no secrets; no `continue-on-error` or `|| true`; YAML parsed independently. |
| First CI run failure | Recorded | The first push failed to start any job because of invalid YAML (`:all: -r` inside a plain scalar); fixed in the next commit. |
| Interpreter assertion | PASS | Cannot pass vacuously; `eol=lf` in `.gitattributes` makes a stray carriage return unlikely. |
| Governance validator on tracked plus untracked-not-ignored files | PASS | A secret-shaped file force-added under `.venv/`, an untracked secret file, a non-text artifact, and a secret in a workflow file are all rejected; no `.git` fails closed. |
| SQL static scan (SEC-05 / TEST-25 static half) | PASS | About 80 mutation cases and whole-tree plants (value-first f-string, concatenation, `%` formatting) all caught. |
| Reformatted files | PASS | Two scripts and one test differ only by formatting (identical syntax trees). |
| Findings from `TASK-02` (F1, F2, F3) | Closed | F1 by the CI job; F3 by the tracked-file scan; F2 reviewed and left unchanged (pyproject and both locks are checked against the same reviewed constants). |

## Findings and dispositions

- M1 (status overstated while the Specs-validation deliverable was open): resolved; JDC chose option 1 (the Code-side pointer check), recorded in the work item.
- M2 (SQL scan false positives and trust gaps): rewritten to judge whole-string statement shapes, require constants to be string literals, cover more statement kinds, and scan `harness/`.
- M3 (required-check text unsupported): the repository policy now states that branch protection is unavailable and required checks are procedural.
- M4 (Gate 3 and non-procedural Gate 8 not listed as deferred): added.
- O1 (the validator's workflow check is a substring test): recorded as deferred; "no required check is advisory" rests on review until a parsed-YAML check exists.
- Understated limits of the SQL scan (a literal constant later extended, name matching ignoring scope): added to the work item.
- Observation: JDC's two decisions are session statements recorded in the repository, not Specs changes.

## Not verified

Python 3.12.15 locally; branch-protection settings (not available on this plan); the Specs repository's own validator from Code CI (not installed by design, option 1).
