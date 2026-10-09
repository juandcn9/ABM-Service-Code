# Work item: TASK-04 — Code CI quality gates

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-04`; `SEC-11`; `SEC-05`/`TEST-25` (static half); `TEST-26`; Gates 3 through 8 as applicable before application code exists
- Decision, gap, or risk records: no new decision or gap; `RISK-0005` (see `docs/governance/deviations.md`, DV-01)
- Owner role: Builder Auditor (Claude Code); independent Tester verification of the final head is required

## Scope

- Objective: make the checks that can run today required CI gates, with no advisory check, and close the `TASK-02` Minor findings scheduled here.
- Included: `quality-gates` job (pinned `setup-python`, exact-patch interpreter assertion, hash-verified dev install, `validate_toolchain.py`, `ruff check`, `ruff format --check`, `mypy`, `pytest`); `tests/security/test_sql_static_scan.py` (no value-formatted SQL, SEC-05/TEST-25 static half); `validate_governance.py` now scans tracked plus untracked-not-ignored files (closes F3); `.gitattributes` LF normalization and `venv/`/`env/` ignores (Observations); mechanical `ruff format` of three existing files; repository-policy and dependency-policy text.
- `TASK-02` findings: F1 closed by the CI job; F3 closed as above; F2 reviewed and left unchanged: `pyproject.toml` and both locks are each checked against the same reviewed constants, so they cannot diverge without failing, and an additional direct comparison would duplicate that.
- Explicit exclusions: running the Specs repository's own `tools/validate_specs.py` from Code CI (see Open decision); gates that need code that does not exist yet (persistence, API/security matrix, operations, release evidence), which later TASKs add to this job; prohibited-data fixture scans beyond the secret patterns (TASK-23); branch-protection settings (not enforceable on this private free-plan repository, see repository policy).
- Dependencies and entry gate: `TASK-01` merged; `TASK-02` Verified and `TASK-03` merged at Code `aa740bb`.

## Acceptance evidence

- Focused tests: `pytest tests/security/test_sql_static_scan.py` (real tree clean; formatted, concatenated, `%`, `.format`, non-literal `execute` rejected; fixed statements and unrelated strings accepted). Force-adding a secret-shaped file under `.venv` makes `validate_governance.py` fail.
- Required broader gates: the `validate-governance` and `quality-gates` CI jobs on the exact head, plus the same commands locally.
- Failure, concurrency, authorization, and recovery cases: not applicable; no behavior exists.
- Documentation/trace updates: README, CHANGELOG, repository policy, dependency policy, this work item.

## Open decision (needs JDC)

The delivery row says "Install Specs validation". The Code repository already validates its pinned Specs pointer (`SPEC_VERSION` against the approved version and SHA) inside `validate_governance.py`, and that now runs as a required gate. Running the Specs repository's own validator, or confirming from CI that the pinned commit is the `v1.0.1` tag commit, needs read access to the private Specs repository, i.e. creating a credential (a deploy key or token stored as a repository secret). The workflow requires explicit human approval for credential creation, so this was not done. Options: (1) accept the pointer check as the Code-side Specs validation; (2) approve a read-only deploy key or token for the Specs repository and a CI step that checks it out at the pinned SHA and runs its validator; (3) make the Specs repository public. Recommendation: option 1 now, option 2 if JDC wants Code CI to prove the pointer against the real Specs tag.

## Implementation notes

- Reversible technical choices: `ALL_CAPS` module constants are allowed as the SQL argument to `execute*`, so fixed statements can live as constants; the scan flags any SQL-looking string built with an f-string, `%`, `+`, or `.format`. Later TASKs may refine it with justification.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI uses the pinned 3.12.15, so this PR also gives the first run on the pinned interpreter.
- The three reformatted files differ only by `ruff format`.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: pending.
- Review findings/resolution: pending.
- Residual risks: required-check enforcement depends on repository settings that this plan cannot enforce; the SQL scan is syntactic and cannot prove absence of injection (TEST-25 runtime half arrives with persistence).
- Next safe action: independent review of this PR and a decision on the Open decision.
