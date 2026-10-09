# Work item: TASK-03 — modular-monolith package layout with boundary checks

**Status:** Implemented

## Authority

- Specs version and exact SHA: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`
- TASK and affected IDs: `TASK-03`; `DEC-0001`; `SEC-12`; `TEST-20` (structural contribution only)
- Decision, gap, or risk records: `DEC-0001`; `RISK-0005` (see Implementation notes); no new decision or gap
- Owner role: Builder (Claude Code); final verification requires an independent Tester in a fresh context

## Scope

- Objective: create the target package layout from `specs/03-architecture.md` section 3 and automated import-boundary tests for the section 4 dependency rules.
- Included files/components: `src/abm/` with `api`, `application`, `domain`, `persistence`, `ports`, `observability`, `main.py`, `config.py`; top-level `harness/`; `tests/{unit,integration,contract,security,e2e}`; pytest and mypy path configuration; `tests/unit/test_import_boundaries.py`.
- Explicit exclusions: any behavior, route, schema, migration, repository/base abstraction, Dockerfile, `compose.yaml`, `infra/`, `migrations/`, `scripts/verify.ps1`, `scripts/demo.ps1`, CI-gate expansion (`TASK-04`), Ponytail pin work (`TASK-05`), dependency changes.
- Dependencies and entry gate: merged `TASK-02` at Code `main` `c768c70a8599d2ea8ba0675447ca36f4c2ad15cf`.

## Acceptance evidence

- Focused tests: `pytest tests/unit/test_import_boundaries.py` checks the layout exists, the real tree has no boundary violations, every `abm` module belongs to a known layer, and the checker rejects forbidden imports (including relative and `from abm import x` forms, `sqlite3`/third-party imports in `domain`, and `harness` imports) while accepting permitted ones; it also rejects `_sqlite3`, `__import__`/`exec`/`eval`, and any `abm` package-root import of a layer or `harness`.
- Required broader gates: `ruff check .`, `mypy src tests scripts`, `scripts/validate_governance.py`, `scripts/validate_toolchain.py`.
- Failure, concurrency, authorization, and recovery cases: not applicable; no behavior exists.
- Documentation/trace updates: README current scope, CHANGELOG, this work item.

## Implementation notes

- Allowed internal imports (reversible technical choice reading section 4): `domain` none; `ports` domain; `application` domain, ports; `persistence` domain, ports; `api` application, domain; `observability` application, domain; `main` all layers and `config`. `config` imports no layer. A later TASK that needs a wider edge must justify it against section 4.
- `TEST-20` (unsupported operations have no route or return `UNSUPPORTED_OPERATION`) cannot be demonstrated before routes exist; it is completed by `TASK-23` and `TASK-25`. This task only supplies the structural guard that nothing outside the layers can be imported inward.
- CI does not yet run `pytest`; wiring it into required checks is `TASK-04`.
- Deviations: the installed Ponytail plugin 5.1.0 in `full` mode (not the Specs-pinned v4.13.0, unverified against the pin) and local Python 3.12.10 (python.org has no Windows binary for the pinned 3.12.15; CI and the container remain pinned) are declared deviations stated by the session user, recorded as DV-01 and DV-02 in `docs/governance/deviations.md` (PR #4). They are not a recorded JDC decision or Specs change, and `RISK-0005` is unchanged.
- `TASK-02` was implemented by another agent; its independent verification record is proposed in a separate PR (#4) and is not a dependency of this change.

## Completion

- Code commit/PR: the exact reviewed branch head and PR are the GitHub record.
- Commands/checks and results: `pytest` (5 passed), `ruff check .`, `mypy src tests scripts`, `validate_governance.py`, `validate_toolchain.py` all pass locally on Python 3.12.10.
- Review findings/resolution:
  - Builder Audit `ponytail-review` (installed plugin 5.1.0, `full` mode; finding input, not authority): dynamic imports were invisible to the domain check; resolved by banning `importlib` in `domain`.
  - Independent fresh-context review of head `f4dd3ab`: PASS with findings, zero Blocker/Major. Minor 1, `import _sqlite3` bypassed the SQLite ban: resolved by banning `_sqlite3`. Minor 2, `abm/__init__.py` was never checked: resolved by checking the package root against the same rules. Minor 3, stale TASK-02 note: updated above.
  - Observation, `__import__`/`exec`/`eval` undetected in `domain`: resolved by rejecting those names in `domain`, which removed the only `shortcut:` marker. `ponytail-debt` now reports 0 markers.
  - Observation, `application` may import `sqlite3`/`fastapi`: section 4 does not forbid it, so it is left as is and recorded here.
  - A fresh-context re-review of the fix diff and independent Tester verification of the final head are still required.
- Residual risks: boundary rules are an interpretation of section 4 and enforced only by tests until `TASK-04` makes them a required check.
- Next safe action: independent review of this PR, then `TASK-04` and `TASK-05`.
