# TASK-38 final gate run on the tag-candidate revision (author run, DV-05 substitute)

**Task:** TASK-38 local handover (DEC-0086). **Revision gated:** `9f1d74e739712842b4d05b1d0da8236ea012e3fb` (`main` after PR #157), checked out detached in a fresh clone, tree clean (0 changes). **Specs:** `v1.9.18` / `507719611c79425fdcfd63d0f5897aed66655db7`. **Date:** 2026-10-13, 20:17:02Z to 20:24:21Z. **Run by:** Claude Code (author), at JDC's request. **Status:** author evidence; the fresh-context Tester reproduction on `d11db54` passed ([`TASK-38-final-gates-tester-report.md`](TASK-38-final-gates-tester-report.md)).

GitHub Actions has started no job since 2026-10-13 18:03Z (billing block). JDC accepted the risk of proceeding without hosted CI verification; deviation DV-05 (`docs/governance/deviations.md`) records it, and this run is the local substitute it describes.

## Environment

| Item | Value |
|---|---|
| Host | Windows 11 (26H2), Python 3.12.10 (pinned 3.12.15 is not published for Windows; DV-02) |
| Docker | engine 29.8.2, Docker Desktop 4.95.0, WSL2 backend (`docker-desktop` distro v2); Resource Saver off |
| Dev tools | from `requirements-dev.lock`, hash-verified install |
| Contract | `contracts/openapi.yaml` at the Specs commit above, sha256 `5e2118b182ca73e1fe3c645d6d726ac1ee48b6c45499b4fdc31c8f87b9c03b36` |

## Results

| Gate (CI job) | Command | Result |
|---|---|---|
| validate-governance | `scripts/validate_governance.py` | PASS |
| quality-gates | `scripts/validate_toolchain.py` | PASS |
| quality-gates | `ruff check .` | PASS |
| quality-gates | `ruff format --check .` | PASS, 195 files (the `.py` and `.md` files ruff checks; 196 at `d11db54`, which adds this file) |
| quality-gates | `mypy src harness tests scripts` | PASS, 102 source files |
| quality-gates | `pytest -q -p no:cacheprovider` | PASS, 1325 passed, 1 warning, 403.68 s |
| http-conformance | `scripts/check_http_conformance.py` on the pinned contract | PASS |
| container-check | focused tests (`test_config`, `test_container_entry`, `test_observability`) | 66 passed |
| container-check | `scripts/check_container.py` | PASS: non-root, read-only app layer, writable data volume, ready, restart |
| container-check | `scripts/smoke_container.py` | PASS: liveness, readiness, registration, authorized read, credit in history and balance, denied requests with no state change |

## Limits

- Windows host and Python 3.12.10, not the Linux CI runner and Python 3.12.15 (the container scripts do run the service on the pinned 3.12.15 image).
- No hosted status; the run is author-attested. The Tester reproduction reduces but does not remove that.
- The revision gated is `9f1d74e`; this evidence file is added after it by a documentation-only change.
- Synthetic data only; no production, backup, restore, disaster recovery, RPO or RTO claim.
