# ABM local service: Windows runbook

ABM (Account Balances Management Service) is a small HTTP service that keeps account balances and an append-only ledger. This guide runs it on one Windows computer with Docker Desktop, using synthetic data only.

> **Run it locally only.** ABM checks the caller identity, role and account scope that a trusted ingress or test harness sends in headers. It does not log people in. Never expose it to untrusted callers or the internet. Keep the port bound to `127.0.0.1`.

## 1. Prerequisites

- Windows 10 or 11 with virtualization enabled.
- Docker Desktop with the WSL2 backend, started. Check from PowerShell:

```powershell
docker --version
docker info --format '{{.ServerVersion}}'
```

The second command must print a version. If it reports that the engine is not running, start Docker Desktop and wait until it says it is running.
- Git, and read access to this repository.
- Port 8000 free on `127.0.0.1`: `Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue` prints nothing.

## 2. Get the exact version

Clone the repository and check out the tag given in the handover message. Keep the clone in a normal folder (not a OneDrive-synced one).

```powershell
git clone https://github.com/juandcn9/ABM-Service-Code.git
cd ABM-Service-Code
git checkout <tag from the handover message>
Get-Content SPEC_VERSION
```

`SPEC_VERSION` shows the Specs release this version implements.

## 3. Build and start

```powershell
docker build -t abm:local .
docker volume create abm-data
docker run -d --name abm --read-only `
  -v abm-data:/data `
  -e ABM_MODE=demonstration -e ABM_TRUSTED_INGRESS=true -e ABM_CLOCK_MODE=system `
  -p 127.0.0.1:8000:8000 abm:local
```

Check that it is ready:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

If the connection is reset right after `docker run`, wait a few seconds and try again. Expected: `status` is `ready`. Until the database is checked, the reply is HTTP 503 with `reason_codes` (for example `DATABASE_UNAVAILABLE` or `INTEGRITY_FAILED`). `GET /health/live` only says the process is up.

## 4. Operate it

| Task | Command |
|---|---|
| Is it running? | `docker ps --filter name=abm` |
| Logs | `docker logs abm` (one JSON line per event; the web access log is off on purpose) |
| Stop | `docker stop abm` |
| Start again | `docker start abm` |
| Remove the container, keep the data | `docker stop abm; docker rm abm`, then repeat the `docker run` command from section 3 |

Data lives in the Docker volume `abm-data`, not in the clone. It survives stop, start and removal of the container. It is lost if the volume is deleted.

**Reset (deletes all local data):**

```powershell
docker stop abm; docker rm abm; docker volume rm abm-data
```

A reset is a fresh start, not a recovery path. Do the same before switching to another version: a volume created by a different version is not covered by this guide.

## 5. Settings

| Setting | Local demonstration (this guide) | Development (`.env.example`) |
|---|---|---|
| `ABM_MODE` | `demonstration` | `development` |
| `ABM_TRUSTED_INGRESS` | `true` (required in `demonstration`) | `false` |
| `ABM_CLOCK_MODE` | `system` (the only accepted value) | `system` |
| `ABM_DB_PATH` | `/data/abm.sqlite3` (image default) | an absolute path |
| `ABM_LOG_LEVEL` | `INFO` | `INFO` |
| `ABM_BUSY_TIMEOUT_MS` | `5000` | `5000` |

Use the left column for this guide. The service refuses to start on an invalid combination and names the setting, never its value: run `docker logs abm`. No secrets are needed.

## 6. Calling the API

The contract is the OpenAPI file for Specs release `v1.9.18`. The owner supplies it separately. Every call carries caller context headers: `X-Caller-Id`, `X-Caller-Role`, `X-Correlation-Id`, plus `X-Account-Scope` for account reads and `Idempotency-Key` for changes. Register an account, then read it:

```powershell
$base = 'http://127.0.0.1:8000'
$reg = @{ 'X-Caller-Id'='demo-registrar'; 'X-Caller-Role'='account_registrar'; 'X-Correlation-Id'='demo-1'; 'Idempotency-Key'='demo-key-1' }
$body = @{ instruction_id='demo-reg-1'; account_id='acct-demo'; customer_id='cust-demo'; currency='USD'; eligibility_reference='elig-demo' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/v1/accounts/registrations" -Headers $reg -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 5

$read = @{ 'X-Caller-Id'='demo-reader'; 'X-Caller-Role'='account_reader'; 'X-Correlation-Id'='demo-2'; 'X-Account-Scope'='acct-demo' }
Invoke-RestMethod -Uri "$base/v1/accounts/acct-demo" -Headers $read | ConvertTo-Json -Depth 5
```

A call without caller context returns HTTP 401. The same instruction with the same `Idempotency-Key` replays the stored result.

## 7. Common problems

| Symptom | Cause and fix |
|---|---|
| `failed to connect to the docker API ... dockerDesktopLinuxEngine` | Docker Desktop is not running. Start it and wait until it says it is running. Quitting it stops `abm`; run `docker start abm` (the data is kept). |
| `port is already allocated` | Something uses port 8000. Stop it, or map another host port (`-p 127.0.0.1:8001:8000`) and use that port in the URLs. |
| `The container name "/abm" is already in use` | `docker rm abm`, then run again. |
| Container exits at start | `docker logs abm` names the invalid `ABM_*` setting. |
| `/health/ready` returns 503 | Read `reason_codes` in the reply and the logs. |

## 8. Version, owner and limits

- Version: the Code tag you checked out, the Specs release in `SPEC_VERSION`, and the image you built (`docker image inspect abm:local --format '{{.Id}}'`).
- Owner and support: JDC. Internal use only; this repository has no licence file.
- Limits: synthetic data only; one service process and one SQLite volume; no production identity or public ingress; no live partner connection. Restart against the intact volume is the only recovery covered; there is no backup, restore, disaster recovery, RPO or RTO claim. Not production ready.
