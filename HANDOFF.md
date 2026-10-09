# Session handoff, 2026-10-09

This file is a handoff record, not a requirement. The approved Specs (`v1.0.1`, commit `5d1cd410399a6fb0154a0117728c409cc7f2ec91`) remain the only authority. It lives on its own branch (`handoff/2026-10-09-session`) and is not meant to be merged into `main`.

## Where things stand

`main` is at `e3aada8` (PR #10 merged). Merged and on `main`: TASK-01 to TASK-05 (TASK-05 as a Blocked work item), TASK-08, TASK-09, plus the verification records for TASK-02 and TASK-03. CI (`validate-governance`, `quality-gates` on CPython 3.12.15) is green on `main`.

| Item | State |
|---|---|
| PR #8 TASK-06 migrations | **Draft, do not merge.** Branch `task-06-migrations`, head `fe3f1bb`. Hardening redesign implemented, tests and review still missing (see below). |
| TASK-07 connection and transactions | Branch `task-07-connection-transactions` (head `6956a66`), pushed, no PR. Needs `main` merged in after PR #8. |
| TASK-10 idempotency and registration | Branch `task-10-registration` (head `68f15d5`), pushed, no PR. Contains older copies of TASK-06 to TASK-09; merge `main` after PR #8. |
| TASK-11 account, history, trace reads | Branch `task-11-reads` (head `ecce3d1`), pushed, no PR. 37 tests pass. Needs `main` merged in. |
| TASK-12 startup and readiness | Branch `task-12-readiness` (head `c0fe18b`), pushed, no PR. Must also call `retained_history_protected()` once PR #8 lands. |
| TASK-05 Ponytail | Work item merged as Blocked. Decision pending (below). |

Branches 07, 10, 11, 12 are stacked: each contains the earlier ones by merge. Open their pull requests only after the earlier ones are merged into `main`, then `git merge origin/main` into the branch so the diff shows only that task. Every merge of `main` conflicts in `README.md` and `CHANGELOG.md` (both append lines); resolve by keeping both sides (delete the conflict marker lines).

## First thing to do next

Finish PR #8 (TASK-06). Nothing downstream can be reviewed cleanly before it.

1. Read `docs/work-items/TASK-06.md` on branch `task-06-migrations`, section "Review findings/resolution". It lists the third review's findings (F1 to F11) and the remaining steps in order.
2. The reason for the redesign: a list of forbidden statements is whack-a-mole (`REPLACE INTO` rewrote retained rows). The runner now snapshots the retained rows, retained schema text, `sqlite_sequence`, temp schema, 19 connection settings, and history before each migration and rolls back on any difference after it. Shipped table and trigger definitions are pinned by SHA-256 in `migrations.py`. The authorizer is the first layer, the comparison is the second, `retained_history_protected()` is the third (readiness).
3. Write the tests: a populated-database attack matrix, an independent oracle, a non-vacuous permissive-authorizer test, one mutation per verification clause and per authorizer rule, tests for the time limit and for false positives. Then wire `retained_history_protected()` into TASK-12 readiness, measure `integrity_check` plus row digests on 50 000 ledger rows, and request a fresh-context review of the final head.
4. Two bugs found while redesigning and already fixed: the authorizer must not block SQLite's own `sqlite_master` writes during `CREATE TABLE` (only `sqlite_sequence` is blocked), and `schema_version` is checked against the expected history, not as retained data.

## Decisions already made by JDC (this session)

- "Install Specs validation" (TASK-04): option 1, the Code-side `SPEC_VERSION` pointer check in the required gate. No credential was created.
- DV-01: the installed Ponytail plugin (5.1.0, `full`) is used instead of the Specs-pinned v4.13.0. DV-02: local Python is 3.12.10 (no Windows binary for 3.12.15). Both are recorded in `docs/governance/deviations.md`; neither is a Specs change, and `RISK-0005` in the Specs is still Draft.
- Migration-runner hardening approved as the correct, risk-free solution (not a risk acceptance).

## Open decisions for JDC

- TASK-05: close the Ponytail pin by (1) an Updater Specs PR adopting 5.1.0, (2) installing v4.13.0 per the Specs with the exact install action approved, or (3) keeping DV-01 indefinitely. Recommendation recorded in `docs/work-items/TASK-05.md`: option 1.
- Specs observations for the Updater (not Code defects): the schema accepts fractional or numeric-text `amount_cents`; an explicit lower ledger `sequence` can be inserted; `idempotency_outcomes` has no immutability trigger; the 128-character scope column cannot hold the specified `customer_id + registration` composite, so Code stores a SHA-256 of the pair (`scope_key`).

## Working rules in force

- One TASK at a time; work item and PR from the templates; the Specs SHA in every PR.
- Every PR gets a fresh-context review (a general-purpose agent, read-only, no GitHub writes) and a Tester pass on the final head. Any Major finding is fixed and re-reviewed. `ponytail-review` runs on each implementation diff; `ponytail-debt` has found no markers.
- JDC merges; the agent never merges. Tell JDC a PR is ready only when both required checks are green on the exact head and its review passed. Branch protection is not available on this plan, so this is procedural.
- A verified TASK is recorded in a small docs-only PR (see the TASK-02 and TASK-03 records and `docs/evidence/`).
- Messages to JDC: only decisions or critical reports, compact, in the form context, recommendation, trade-offs.
- `CLAUDE.md` in the Code repo stays untracked and is never committed.

## Environment notes

- Use `.venv\Scripts\python.exe` (Python 3.12.10). The `python` on PATH is a Microsoft Store stub. Install with `python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.lock`.
- Gates to run locally: `pytest`, `ruff check .`, `ruff format --check .`, `mypy src harness tests scripts`, `scripts/validate_governance.py`, `scripts/validate_toolchain.py`.
- The GitHub CLI token now has the `workflow` scope (needed to push workflow changes). A global git credential helper for `gh` was added earlier in the session.
- Editing hazards on this Windows shell: write files with the editor tool, not shell heredocs containing backslash escapes; avoid Python one-liners with `\n` inside quoted strings; `ruff` flags unparenthesized implicit string concatenation in collections (ISC004), fix with `ruff check --select ISC004 --fix --unsafe-fixes`; `sleep` followed by a command is blocked, use the monitor tool for waiting.
- Scratch files used during the session sit in the system temp directory and are disposable.

## Later tasks (not started)

TASK-13 to TASK-35 follow `specs/09-delivery-plan.md`: ACH, transfer, card flows; concurrency and fault tests; corrections, restriction, closure, retention; API routes (use `strict_json` and one normalized header mapping, and limit body size); observability; container; restart tests; AWS reference; release. The `fingerprint` field set for each new operation must be tested so that every effect-relevant field changes it, and optional fields must be normalized (absent versus null).
