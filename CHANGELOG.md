# Changelog

All notable Code repository changes are recorded here.

## [Unreleased]

- Established `TASK-01` repository governance, templates, CI validation, and the immutable Specs `v1.0.1` pointer without runtime dependencies or service behavior.
- Pinned the `TASK-02` Python/runtime/development toolchain, hash locks, safe example configuration, and official container-base digest without adding service behavior.
- Added the `TASK-03` modular-monolith package layout and automated import-boundary tests without service behavior.
- Added the `TASK-04` required `quality-gates` CI job (pinned Python, hash-verified install, toolchain, lint, format, type, tests), a static SQL-formatting scan, LF normalization, and a tracked-file secret scan.
- Added `TASK-06` forward-only SQLite migrations: migration `0001` equal to the approved schema contract, a checksum-validating runner, and integration tests.
- Added `TASK-08` domain value objects (integer-cent USD money, canonical identifiers and UTC instants), typed results with stable error codes, a canonical idempotency fingerprint, and the controllable clock port with a deterministic test double; CI type-checks `harness` too.
- Added `TASK-07` strict SQLite connection settings (foreign keys, WAL, full synchronous, bounded busy timeout), an all-or-nothing write transaction with `BEGIN IMMEDIATE`, a snapshot read transaction, and safe SQLite error mapping.
- Added `TASK-09` trusted caller-context parsing, the deny-by-default role and account-scope authorization matrix, and strict transport validation helpers (strict JSON, exact fields, path/body account agreement) with security tests.
- Added the `TASK-05` work item (Blocked on the Ponytail pin decision) and wired the Ponytail review commands into the repository policy.
- Added `TASK-10` transactional idempotency (stored exact replay, conflict without effect, deterministic rejections), the first storage ports with a SQLite unit of work, and idempotent account registration creating one zero-state account with its retention row and trace.
- Completed the repository policy with the controls the Specs require (human approval before risky actions, severity handling, lifecycle status values, approval and merge authority), aligned the pull-request template with the Specs template, and tightened the governance validator (anchored checks for the workflow, `.gitignore`, template fields, policy topics, work-item statuses, payment-card numbers, NUL bytes).
- Hardened the governance validator after re-verification: the CI workflow is pinned by a whole-file digest, `.gitignore` is checked with git's own matching (no nested files, no re-inclusion), template and policy checks ignore comments and code fences, card numbers written in groups are detected, and `docs/short-purpose` branches, the Cursor controls, and the other missing policy clauses are documented (deviation DV-03 records the version-neutral template wording).
- Recorded the independent verification of `TASK-04`, `TASK-08`, and `TASK-09` (sanitized Tester reports under `docs/evidence/`) and refreshed the README scope.
