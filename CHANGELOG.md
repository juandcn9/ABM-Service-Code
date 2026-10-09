# Changelog

All notable Code repository changes are recorded here.

## [Unreleased]

- Established `TASK-01` repository governance, templates, CI validation, and the immutable Specs `v1.0.1` pointer without runtime dependencies or service behavior.
- Pinned the `TASK-02` Python/runtime/development toolchain, hash locks, safe example configuration, and official container-base digest without adding service behavior.
- Added the `TASK-03` modular-monolith package layout and automated import-boundary tests without service behavior.
- Added the `TASK-04` required `quality-gates` CI job (pinned Python, hash-verified install, toolchain, lint, format, type, tests), a static SQL-formatting scan, LF normalization, and a tracked-file secret scan.
- Added `TASK-06` forward-only SQLite migrations: migration `0001` equal to the approved schema contract, a checksum-validating runner, and integration tests.
- Added the `TASK-05` work item (Blocked on the Ponytail pin decision) and wired the Ponytail review commands into the repository policy.
