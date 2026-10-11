# Work item: TASK-26 — structured logs, bounded metrics, safe health, and the TEST-39 / TEST-41 facets

**Status:** Draft

## Authority

- Specs version and exact SHA: `v1.9.11` / `d2211b53a0570437b7fa9ddb1a1ba46969d6ac40` (DEC-0056). The Specs plan (`specs/09-delivery-plan.md`, TASK-26) is the record that makes this item ready once D1 to D4 are decided.
- TASK and affected IDs: `TASK-26`; `DEC-0051` (structured-log, metric, correlation and runtime-redaction facets); `DEC-0053` (TEST-39 and TEST-41 facets); `SEC-09`; `NFR-07`; `INV-12`; `INV-14`; `BT-07`; `TEST-26` (log facet); `TEST-29`; `TEST-39`; `TEST-41`.
- Dependencies: `TASK-12` (Verified) and `TASK-25` (Verified; Code PR #95, merged `2c439fd`; record PR #96, merged `328f98b`).
- Owner role: Builder (Claude Code); independent Tester verification of the final head is required.

## Dependency check

- `TASK-25` is Verified: the HTTP binding, envelopes, and the health routes are on `main`. The health routes are the only public surface TASK-26 may touch.
- `TASK-12` is Verified in the plan (reason-code mapping).

## Scope (proposed; each item depends on a decision below where marked)

1. **Structured logs (SEC-09, TEST-29).** One JSON line per request and per command outcome, with an allowlisted field set: correlation id, operation, safe result code, duration, caller role. Request bodies and opaque evidence are never logged. Identifiers are omitted or one-way tokenized (per DEC-0051, TEST-24).
2. **Bounded metrics (TEST-29).** In-process counters keyed by bounded labels only (operation, result code). No account, movement, or caller identifier as a label. Metrics are emitted as structured events (see D2).
3. **Safe health (NFR-07, TEST-26).** Health output carries only reason codes already in the contract. Nothing else changes in `/health/*`.
4. **TEST-41 facet.** Each permitted and rejected account or trace read emits one attributable security event (caller id, role, scope, operation, result code) with no returned financial data. No schema change.
5. **TEST-39 facet (BT-07, INV-12).** A time-driven scan finds pending ACH or card items older than a threshold and emits a safe escalation event per item (item reference, state, age). The scan posts no money, releases no hold, and changes no state (proven by the existing invariant checks after the scan).
6. **Evidence manifest generation (TASK-26 row).** A script writes a manifest of the revisions and the scan results. TASK-34 owns the bundle; TASK-26 owns the manifest file format only (see D4).

## Decisions required from JDC

- **D1. Aged threshold.** The spec defines no age (BT-07 says only "aged"). Options: (a) a fixed default of 7 days, configurable by a setting, recorded as a DEC; (b) no default: the scan requires an explicit threshold argument and tests pass one. Trade-off: (a) gives an operator a working default but invents a number; (b) keeps the spec silent but leaves the escalation unused until configured. Recommendation: (b), with the threshold passed in by the caller, so no number is invented.
- **D2. Escalation and metric sink.** DEC-0053 forbids a new public interface. Options: (a) structured JSON lines on stdout, one line per event; (b) a log file path from configuration. Trade-off: (a) needs no new config and fits the container log model in NFR-07; (b) needs a new setting and a writable path. Recommendation: (a). Metrics also go out as events on the same stream, with no `/metrics` route.
- **D3. Trigger for the aged scan.** No scheduler exists, and the spec adds none. Options: (a) the scan is a function plus a script entry point, run by an operator or test, with no HTTP route; (b) a route under `/v1/...`. Trade-off: (b) breaks DEC-0053 and the contract; (a) leaves scheduling to TASK-27. Recommendation: (a).
- **D4. Manifest scope.** Options: (a) TASK-26 writes a manifest file with exact revisions and scan results, and TASK-34 bundles it; (b) TASK-26 writes nothing and the manifest moves to TASK-34. Trade-off: (a) keeps the TASK-26 row as written; (b) defers more work. Recommendation: (a), limited to the file format and generation, no bundle.

## Non-claims (until implemented and tested)

- No production log shipping, log retention, or alerting. Those belong to TASK-27 and the reference architecture.
- No readiness wiring of a real database check (already recorded as a scheduled item for TASK-26 or TASK-27 in TASK-25).
- No concurrency or throughput claim for the metric counters (single process, DEC-0055).

## Scheduled items

- Container, scheduler, and any CI execution of the aged scan: TASK-27.
- Evidence bundle assembly and scan: TASK-34.
