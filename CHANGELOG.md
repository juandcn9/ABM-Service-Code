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
