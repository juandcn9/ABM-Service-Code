# Work item: TASK-04 — Code CI quality gates

**Status:** Verified

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-04`; `SEC-11`; `SEC-05`/`TEST-25` (static half); `TEST-26`; Gates 3 through 8 as applicable before application code exists
- Decision, gap, or risk records: no DEC or GAP record created; one JDC decision (Specs-validation option 1) is recorded below; `RISK-0005` (see `docs/governance/deviations.md`, DV-01)
- Owner role: Builder Auditor (Claude Code); independently verified (see Independent verification)

## Scope

- Objective: make the checks that can run today required CI gates, with no advisory check, and close the `TASK-02` Minor findings scheduled here.
- Included: `quality-gates` job (pinned `setup-python`, exact-patch interpreter assertion, hash-verified dev install, `validate_toolchain.py`, `ruff check`, `ruff format --check`, `mypy`, `pytest`); `tests/security/test_sql_static_scan.py` (no value-formatted SQL in `src/abm` and `harness`, SEC-05/TEST-25 static half); `validate_governance.py` now scans tracked plus untracked-not-ignored files (closes F3); `.gitattributes` LF normalization and `venv/`/`env/` ignores (Observations); mechanical `ruff format` of three existing files; repository-policy and dependency-policy text.
- `TASK-02` findings: F1 closed by the CI job; F3 closed as above; F2 reviewed and left unchanged: `pyproject.toml` and both locks are each checked against the same reviewed constants, so they cannot diverge without failing, and an additional direct comparison would duplicate that.
- Explicit exclusions: running the Specs repository's own `tools/validate_specs.py` from Code CI (see Decision); Gate 3 beyond running `pytest` (no domain code exists yet), Gates 5, 6, 7 (persistence, API/security matrix, operations), and the non-procedural parts of Gate 8 (conformance review, `ponytail-audit` at phase/release boundaries), which later TASKs add; machine enforcement of the workflow's own structure (the validator's workflow check is a substring test, so "no required check is advisory" rests on review until a parsed-YAML check exists; recorded for `TASK-05` or a later approved task); prohibited-data fixture scans beyond the secret patterns (TASK-23); branch-protection settings (not enforceable on this private free-plan repository, see repository policy).
- Dependencies and entry gate: `TASK-01` merged; `TASK-02` Verified and `TASK-03` merged at Code `aa740bb`.

## Acceptance evidence

- Focused tests: `pytest tests/security/test_sql_static_scan.py` (real tree clean; formatted, concatenated, `%`, `.format`, non-literal `execute` rejected; fixed statements and unrelated strings accepted). Force-adding a secret-shaped file under `.venv` makes `validate_governance.py` fail.
- Required broader gates: the `validate-governance` and `quality-gates` CI jobs on the exact head, plus the same commands locally.
- Failure, concurrency, authorization, and recovery cases: not applicable; no behavior exists.
- Documentation/trace updates: README, CHANGELOG, repository policy, dependency policy, this work item.

## Decision (JDC, 2026-10-09)

The delivery row says "Install Specs validation". The Code repository already validates its pinned Specs pointer (`SPEC_VERSION` against the approved version and SHA) inside `validate_governance.py`, and that now runs as a required gate. Running the Specs repository's own validator, or confirming from CI that the pinned commit is the `v1.0.1` tag commit, needs read access to the private Specs repository, i.e. creating a credential (a deploy key or token stored as a repository secret). The workflow requires explicit human approval for credential creation, so this was not done. Options: (1) accept the pointer check as the Code-side Specs validation; (2) approve a read-only deploy key or token for the Specs repository and a CI step that checks it out at the pinned SHA and runs its validator; (3) make the Specs repository public. JDC chose option 1 in the Claude Code session on 2026-10-09: the Code-side pointer check in the required `validate-governance` gate satisfies "Install Specs validation" for this task. No credential was created, and Code CI does not prove the pointer against the real Specs tag; if that is wanted later, option 2 needs a new explicit approval. This is a statement in the session, not a Specs change; the delivery plan row is unchanged.

## Implementation notes

- Reversible technical choices: the SQL argument to `execute*` must be a string literal or a module-level name bound to a plain string literal anywhere in the scanned tree, so fixed statements can live as constants. The scan flags a string built with an f-string, `%`, `+`, or `.format` whose known text has the shape of a statement (`SELECT … FROM`, `INSERT INTO`, `UPDATE x SET`, `PRAGMA`, `VACUUM`, `ATTACH`, and similar), with interpolated values counted as one token. Known limits: constants are matched by name across the whole scanned tree, ignoring scope, so a function parameter or local that shares a name with a literal constant elsewhere is trusted; a literal constant that is later extended (`Q += x`, `Q = Q + x`) is still trusted; aliasing (`run = cur.execute`), `getattr` indirection, SQL assembled from pieces where the literal is not first, other driver methods such as `exec_driver_sql`, and a `SELECT` whose text starts with an English phrase can be misjudged. It is syntactic and does not prove absence of injection; the runtime half of TEST-25 arrives with persistence. Later TASKs may refine it with justification.
- Installed Ponytail plugin 5.1.0 (`full`) and local Python 3.12.10 are declared deviations DV-01 and DV-02; CI uses the pinned 3.12.15, so this PR also gives the first run on the pinned interpreter.
- The three reformatted files differ only by `ruff format`.

## Completion

- Code commit/PR: PR #5, merged as `4dacac2`.
- Commands/checks and results: locally (Python 3.12.10) `pytest` 9 passed, `ruff check`, `ruff format --check`, `mypy src tests scripts`, `validate_governance.py`, `validate_toolchain.py` pass. In CI on Linux with `Successfully set up CPython (3.12.15)` and the exact-patch assertion passing, the `quality-gates` and `validate-governance` jobs pass on the PR head. This is the first run on the pinned interpreter and the first non-Windows run of the test suite. The first push failed to start any job because the workflow YAML was invalid (`:all: -r` inside a plain scalar); fixed in the next commit. Nothing in this repository parses workflow YAML locally, so CI is the only syntax check.
- Review findings/resolution: Builder Audit `ponytail-review` (installed plugin 5.1.0, `full`, DV-01) found nothing to fix; the first-version SQL scan limit (an f-string starting with an expression) was superseded by the rewrite below. Independent fresh-context review of head `44830ab`: PASS with findings, zero Blocker/Major. M1 (status overstated while the Specs-validation deliverable was open): status was set to Blocked with the blocker named, and is Implemented again after JDC chose option 1. M2 (SQL scan false positives and trust gaps): rewritten to match whole-string statement shapes, resolve constants to plain string literals, cover more statement kinds and `harness/`, and assert files were scanned. M3 (policy text dangling): repository policy now states plainly that branch protection is unavailable and required checks are procedural. M4 (Gate 3 and Gate 8 not in the deferral list): added to exclusions. O1 (workflow check is a substring test): recorded as an exclusion above. O2/O3: noted, no change. Independently verified (see Independent verification). A second independent review of head `870ddb3` found PASS with findings (zero Blocker/Major): stale text in this work item (corrected here) and the understated SQL-scan limits (added above); both required checks were green on that head on CPython 3.12.15.
- Residual risks: required-check enforcement depends on repository settings that this plan cannot enforce; the SQL scan is syntactic and cannot prove absence of injection (TEST-25 runtime half arrives with persistence).
- Next safe action: merge only with both required checks green on the exact head SHA (procedural, no branch protection available); then `TASK-05`.

## Independent verification

- Role and context: Tester, fresh-context agents that did not build `TASK-04`, 2026-10-09. The sanitized report is committed at [`docs/evidence/TASK-04-tester-report.md`](../evidence/TASK-04-tester-report.md).
- Revision tested: Code PR #5 head `870ddb31e9dd6a5820c33f5914f4357c98194576`; the merged head `cc5e93a` (merge commit `4dacac2`) differs only by documentation wording responding to the review, and CI passed on it. Specs `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Result: PASS with findings; zero Blocker, zero Major. The four findings of the first review (labeled M1 to M4 in the report) are resolved; the Observation that the validator's workflow check is a substring test stays open (see below).
- Scope of "Verified": the CI gates, SQL static scan, tracked-file secret scan, and the closure of the `TASK-02` Minor findings, on the pinned interpreter in CI. Gates 5, 6, 7, the non-procedural parts of Gate 8, and machine enforcement of the workflow's own structure are deferred and recorded in this work item.
- Not verified: Python 3.12.15 locally (CI covers it); branch-protection settings (unavailable on this plan; the controls are procedural).
