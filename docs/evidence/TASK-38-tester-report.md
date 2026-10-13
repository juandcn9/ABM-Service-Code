# TASK-38 clean-run report (author-assisted, not the independent Tester pass)

**Task:** TASK-38 local handover (DEC-0086). **Code commit:** `df14a95a62868b619f6ec6edca66c863a2909850` (fresh clone of `main`, in a Desktop folder outside OneDrive). **Specs:** `v1.9.18` / `507719611c79425fdcfd63d0f5897aed66655db7`. **Date:** 2026-10-13. **Run by:** JDC, commands as in the runbook; Claude Code reviewed each transcript. This is not the independent Tester pass, which is still pending.

## Environment

| Item | Value |
|---|---|
| Windows | 11, version 26H2 (as reported by JDC) |
| Docker engine | 29.8.2 (build 7fc2dff), Compose v5.6.0 |
| Docker context | Docker Desktop, storage driver `overlayfs` |
| Docker Desktop app version | Not captured |
| WSL2 backend | Not captured (`docker info` does not name it) |
| Port 8000 free check (`Get-NetTCPConnection`) | Not captured |

## Results

| Step | Result |
|---|---|
| Clone and `git rev-parse HEAD` | `df14a95a62868b619f6ec6edca66c863a2909850` |
| `docker build -t abm:local .` (cached) and `docker build --no-cache` | Both finished. The cold build re-ran `pip install --require-hashes`. |
| `docker run` (section 3) and `/health/ready` | `status: ready` |
| `docker ps`, `docker logs abm` | Running on `127.0.0.1:8000->8000`; JSON request line; no errors |
| Register `acct-demo`, then read it | `registration_state: created`; account `open`, restriction `none`, all balances 0 |
| Same POST with the same `Idempotency-Key` | Stored result, `meta.replayed: true` |
| Call without caller headers | HTTP 401, `UNAUTHORIZED` |
| `docker stop abm` then `docker start abm` | Ready; `acct-demo` still `open` |
| `docker stop abm; docker rm abm` then `docker run` on the same volume | Ready; `acct-demo` still `open` |
| Cold-built image on the existing volume | Ready; `acct-demo` still `open` |
| `ABM_TRUSTED_INGRESS=false` | `CONFIG_INVALID: ABM_TRUSTED_INGRESS`, exit 1 |
| Port 8000 busy | `Bind for 127.0.0.1:8000 failed: port is already allocated` |
| Docker Desktop quit | `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine ...`. `abm` stayed `Exited (0)`; `docker start abm` restored it with the data intact. |

## Observations

| ID | Observation | Disposition |
|---|---|---|
| O-01 | Straight after `docker run` on the cold-built image, the first `/health/ready` and the account read failed with a reset connection. The same commands succeeded on the next attempt, with no change. Container logs were not captured for the failed attempt, so the cause (probably the service not yet listening) is not confirmed. | Runbook now says to wait and retry. The Tester pass should watch for it. |
| O-02 | The runbook said `docker: error during connect` when Docker is stopped. The real text is the `failed to connect to the docker API ...` message above. | Runbook section 7 corrected. |
| O-03 | After Docker Desktop restarts, `abm` stays stopped. | Runbook section 7 says to run `docker start abm`. |
| O-04 | `Invoke-RestMethod` hides nested fields (`@{...}`) without `ConvertTo-Json`. | Runbook examples now pipe to `ConvertTo-Json -Depth 5`. |
| O-05 | Image identifiers differ between builds of the same commit. The cached builds and the cold build gave different image manifests and configs. | `HANDOVER.md` will record the identifier of the build used, labelled build-specific. |

Cold-build image identifier (`docker image inspect abm:local --format '{{.Id}}'`): `sha256:d52e2ce0b0fe760cc59a1dbc999e89caab7a9f37f1ab2a77198066a2d5c90ab8`.

## Not covered

The independent Tester pass; Docker Desktop app version; WSL2 backend proof; the port-free precheck. Synthetic data only; no production, backup, restore or recovery claim.
