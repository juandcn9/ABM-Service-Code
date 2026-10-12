# Work item: TASK-29 — intact-volume restart as the only supported recovery; no backup or disaster-recovery claim

**Status:** Verified

Tester PASS on the merged revision `e95fe56` (PR #117; PR head `8f42e70`): `docs/evidence/TASK-29-tester-report.md`. JDC decided Verified on the criteria: Tester PASS on the merged revision, acceptance met.

## Authority

- Specs version and exact SHA: `v1.9.12` / `1f6a26d379f82ce0cb227b02d7e197fb4bb99b2f` (Code pin). Specs `main` includes TASK-29's row in `specs/09` (Draft).
- TASK and affected IDs: `TASK-29`; `NFR-08` (demonstration recovery limited to restart against the intact mounted volume; backup/restore and disaster recovery unclaimed); `TEST-32` (documentation, demo automation, and the AWS reference make no backup, restore, disaster-recovery, RPO, or RTO claim).
- Dependencies: `TASK-27` (Verified) and `TASK-28` (Verified; merged `48d7c13`).
- Owner role: Builder (Claude Code); independent Tester verification of the merged head is required.

## Scope

- Objective: state the supported recovery in the documentation, and prove by an automated check that no document or demonstration script claims backup, restore, disaster recovery, RPO, or RTO.
- Included:
  1. `README.md`: a Recovery section stating that supported demonstration recovery is restart of the same version against the intact mounted SQLite volume, with the readiness integrity check, and listing what is not claimed.
  2. `tests/unit/test_recovery_claims.py` (TEST-32): every line in the README, Dockerfile, `.dockerignore`, `docs/` (outside `docs/evidence/`), `scripts/`, and `.github/` workflows that names a recovery term (backup, restore, disaster, RPO, RTO) must also disclaim it. The test also checks that the scan reads the documentation it is meant to cover, and that the supported-recovery statement is present.
- Explicit exclusions:
  - The AWS reference (TASK-30). When it exists, its files join the scan scope; this work item does not create them.
  - Evidence reports (`docs/evidence/`) record mutant labels and test names, not product claims; they are not scanned.
  - No change under `src/`.

## Acceptance evidence

- Focused tests: `tests/unit/test_recovery_claims.py` passes; a deliberately unqualified statement is flagged (checked by hand before the test was written).
- Required broader gates: full pytest, ruff check and format, mypy, both validators, and CI on the exact PR head.
- Documentation and trace updates: this work item; the README Recovery section.

## Non-claims

- No backup, restore, disaster-recovery, RPO, or RTO claim.
- The check reads the words on each line; it cannot judge a claim that avoids those words. A reviewer remains responsible for wording that paraphrases a recovery claim.

## Completion

- Code commit/PR: branch `feat/task-29-recovery` from `main`; PR not yet opened.
- Commands/checks and results: full pytest on `e95fe56`: 999 passed; ruff, format, mypy and both validators pass; scan adversarial cases pass.
- Review findings/resolution: Tester PASS (no Blocker or Major). Notes: a paraphrased claim without a listed term is not caught (accepted limit); the stale README non-claim line is corrected in the Verified record PR.
- Residual risks: the term list is fixed; a paraphrased claim without those words is not caught.
- Next safe action: open the Code PR, run CI, then the Tester pass on the merged head.
