# TASK-03 independent Tester report (sanitized record)

**Provenance:** final report returned by a fresh-context Tester agent on 2026-10-09, launched by the Claude Code session that built `TASK-03`. The Tester derived its checks from the Specs before reading the work item. The Builder only reformatted the report. It is evidence input, not Specs authority.

- Revision tested: Code `main` `aa740bb6751b0ed459ef72a7f72884db20f641b1` (merge of PR #4 on top of PR #3), from a detached worktree.
- Specs: `v1.0.1` / `5d1cd410399a6fb0154a0117728c409cc7f2ec91`.
- Environment: Python 3.12.10 on Windows 11, throwaway virtual environment from `requirements-dev.lock` (`--require-hashes --only-binary=:all:`). Not covered: Python 3.12.15, Linux, and the `quality-gates` CI job (introduced later by `TASK-04`).

## Result

PASS with findings. Zero Blocker, zero Major, two Minor, four Observations. Verified for the structural layout and static import-boundary rules.

## Checks

| # | Check | Result | Evidence summary |
|---|---|---|---|
| 1 | Layout matches the in-scope part of the section 3 tree | PASS | `src/abm/{api,application,domain,persistence,ports,observability}`, `main.py`, `config.py`, `harness/`, and `tests/{unit,integration,contract,security,e2e}` exist. |
| 2 | Nothing out of scope | PASS | 22 files changed from `c768c70`; only the layout, the test, docs, the TASK-02 record, and 8 lines of `pyproject.toml` (pytest and mypy path settings). No lock, script, CI, Dockerfile, compose, infra or migration change; every new `.py` file is docstring-only. |
| 3 | pytest | PASS | 5 passed; each test alone passes; passes from another working directory. |
| 4 | `ruff check .` | PASS | All checks passed. |
| 5 | `ruff format --check .` | FAIL at `aa740bb` | Three files would be reformatted (two `TASK-02` files and the `TASK-03` test). Closed by `TASK-04`, which reformatted them and added the check to CI. |
| 6 | `mypy src tests scripts` | PASS | No issues in 12 files. |
| 7 | `validate_governance.py`, `validate_toolchain.py` | PASS | Both pass. |
| 8 | CI at `aa740bb` | PASS, limited | One job, `validate-governance`, passed; it does not run pytest, ruff or mypy. |
| 9 | Adversarial import probes | PASS with misses | See below. |
| 10 | Mutation tests | PASS | One injected violation at a time in a scratch copy of real modules; each made exactly one test fail (`sqlite3`, `abm.api` from domain, `persistence` from api, `harness` from persistence and main, third-party import in a namespace file, application to observability, config to domain, package root to api, `__import__` in domain, an unknown module, a deleted `ports/`). The real-tree test is not vacuous. |
| 11 | Determinism and order independence | PASS | No network, time or randomness; results identical when run singly and from another directory. Only one test file exists, so cross-file order is not exercised. |

## Adversarial probes

All 30 ordered layer pairs behave exactly as the allowed-edge table says. Caught: relative imports at depth 1, 2 and 3; `from abm import x`; `import abm.x as y`; star imports; `TYPE_CHECKING`, function-local and try/except imports; in `domain`: `sqlite3`, `_sqlite3`, `importlib`, `pydantic`, `starlette`, `typing_extensions`, and `__import__`/`exec`/`eval`; `harness` from any layer, `main`, `config` or the package root; the package root importing a layer; unknown modules and namespace directories. A syntax error fails closed.

Not enforced (judged by the Tester against section 4): `__import__`/`importlib` outside `domain`; attribute and indirect forms of dynamic import in `domain` (`builtins.__import__`, `getattr(builtins, ...)`, `compile`, `runpy`, `globals()[...]`); `import abm` followed by attribute access; third-party and standard-library imports outside `domain` (for example `application` importing `fastapi` or `sqlite3`); packages under `src/` outside `abm`; the "observability never derives financial truth" rule (not statically testable).

## Allowed-edge table versus section 4

Matches the explicit rules for `domain`, `application`, `persistence`, `api` and `main`. It adds `ports` (domain only), which section 4 does not mention. Stricter than the text: `persistence` cannot import `application`; `api` cannot import `ports`; only `main` may import `config`. Looser: `api` may import `domain`; `observability` may import `application` and `domain`; third-party and stdlib imports are unconstrained outside `domain`.

## Findings

- **F1, Minor.** `ruff format --check .` failed at `aa740bb`. Resolved by `TASK-04` (format check is now a required CI gate).
- **F2, Minor.** The work item named no SHA or PR number in its Completion section and kept pending items after verification. Resolved by the verification record.
- **O1, Observation.** Dynamic-import and attribute-form gaps above.
- **O2, Observation.** Third-party and stdlib imports are unrestricted outside `domain`; a later task could tighten `application`, `ports` and `persistence`.
- **O3, Observation.** `ALLOWED["config"]` and `ALLOWED["main"]` are special cases; `from _typeshed import x` in `domain` would be a harmless false positive.
- **O4, Observation.** CI at `aa740bb` did not run pytest, ruff or mypy; `mypy src tests scripts` omits `harness/`, which is empty.

## TEST-20

Acceptable and not overclaimed: `TEST-20` needs routes, which do not exist. `TASK-03` is a structural contribution only; completion belongs to `TASK-23` and `TASK-25`. `SEC-12` and `TEST-20` must not be recorded as satisfied by `TASK-03`.

## Not verified

Python 3.12.15; Linux or CI execution of pytest at `aa740bb`; the correctness of earlier reviews; the effect of later PRs.
