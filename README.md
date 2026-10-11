# OpsPilot

OpsPilot is an incident investigation console for SRE and backend teams. It brings incident-scoped evidence into a checkpointed investigation, checks deterministic cause signatures, and lets an operator request a typed simulator action for review by the separate approver role.

**Investigate with evidence. Keep every action behind a role-gated approval and server verification.**

Use the same application through its browser console, interactive CLI, or versioned API. The guided case uses bundled scenario evidence; configured alert, normalized-evidence, and Prometheus inputs are also supported, and read-only MCP tools are available. Actions change simulator state only.

The website has one introduction page at `/`; **Get started** opens the console at `/console`. The console's six navigation items are views in that same application.

**Start here:** [Quick start](#quick-start) · [Guided walkthrough](#guided-walkthrough) · [CLI-only package](#cli-only-package) · [Connect a service](#connect-an-existing-service) · [API and integrations](#api-and-integrations) · [Verification](#development-and-verification)

## Quick start

### Requirements

- Python 3.11–3.14
- Git to clone the repository
- Node.js 24 only for the JavaScript syntax check

The API and browser console run together. The CLI-only package needs no Node.js or frontend assets.

### Windows PowerShell

```powershell
git clone https://github.com/Jithendra-coder/OpsPilot.git
Set-Location OpsPilot
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Keep this server terminal open. At first start, copy the one-time operator and approver passwords printed there. They are generated in memory and change after restart unless explicitly configured. Open <http://127.0.0.1:8765>, then select **Get started** for the console. For the CLI, open a second terminal in the repository:

```powershell
.\.venv\Scripts\python.exe -m scripts.cli
```

### macOS and Linux

```sh
git clone https://github.com/Jithendra-coder/OpsPilot.git
cd OpsPilot
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

In a second terminal run `.venv/bin/python -m scripts.cli`. The API listens on loopback at `127.0.0.1:8765` by default.

## Guided walkthrough

1. Open `http://127.0.0.1:8765`, choose **Get started**, and sign in with the operator password printed by the server.
2. Select **Run guided incident** for `SCN-001`, open the incident, and start its read-only investigation.
3. Review the log, metric, trace, and change observations, then inspect the diagnosis and report.
4. Request the eligible allowlisted action. This creates a proposal; it does not execute the action.
5. Sign out, use the approver password to review the exact parameters, and approve the proposal.
6. Sign out, return with the operator password, execute the approved action once, and inspect the simulator verification and report.

OpsPilot enforces separate operator and approver roles. The credentials are shared locally, so the demo shows role separation; it does not prove that two distinct people participated.

### Repeatable local credentials

Use distinct random passwords of at least 16 characters. These PowerShell commands keep values in the current process environment, not in the repository:

```powershell
$env:OPSPILOT_PASSWORD = (.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
$env:OPSPILOT_APPROVER_PASSWORD = (.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
.\.venv\Scripts\python.exe app.py
```

On macOS/Linux, generate values with Python or load them from a protected secret manager. Do not commit credentials. If unset, use the one-time values printed by the server.

### Container deployment (full repository)

The CLI-only bundle does not include a Dockerfile or web assets. From the full repository, build the image:

```sh
docker build -t opspilot:local .
```

The container binds internally to `0.0.0.0`, so startup requires distinct configured operator/approver passwords (16+ characters), `OPSPILOT_ALLOW_REMOTE=true`, an exact HTTPS `OPSPILOT_PUBLIC_ORIGIN`, and `OPSPILOT_COOKIE_SECURE=true`. Put these values in a protected environment file, terminate TLS at a trusted reverse proxy, and keep the published app port loopback-only:

```dotenv
OPSPILOT_PASSWORD=<unique-random-operator-password>
OPSPILOT_APPROVER_PASSWORD=<different-random-approver-password>
OPSPILOT_ALLOW_REMOTE=true
OPSPILOT_PUBLIC_ORIGIN=https://ops.example.com
OPSPILOT_COOKIE_SECURE=true
```

Replace the example origin and passwords. Keep this file out of source control and restrict its filesystem permissions.

```sh
docker run --detach --name opspilot --restart unless-stopped \
  --publish 127.0.0.1:8765:8765 \
  --volume opspilot-data:/data \
  --env-file /etc/opspilot/opspilot.env \
  opspilot:local
```

See the [runbook](docs/runbook.md) for reverse-proxy and secret-storage requirements.

## CLI-only package

The CLI connects to an OpsPilot API. The bundle also contains the minimal Python API server needed to run a local instance. It excludes the browser UI, demo media, README/docs, tests, Git metadata, and package-builder script.

### Build it

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.package_cli
```

This produces `dist/opspilot-cli/` and `dist/opspilot-cli.zip`. The package folder contains exactly:

```text
app.py
requirements.txt
backend/                 API, investigation, evidence, integrations
  __init__.py
  asgi.py
  investigation_tools.py
  llm.py
  mcp_server.py
  prometheus.py
  telemetry.py
  workflow.py
scripts/
  __init__.py
  backup.py
  cli.py
  evaluate.py
  smoke_load.py
```

The builder verifies the folder and ZIP contents and refuses to overwrite existing outputs. Remove both generated paths before rebuilding. To pick another new destination:

```powershell
.\.venv\Scripts\python.exe -m scripts.package_cli --output C:\OpsPilot\opspilot-cli
```

### Install and run on Windows

Extract the folder or ZIP to `C:\OpsPilot\opspilot-cli`, then run:

```powershell
Set-Location C:\OpsPilot\opspilot-cli
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Keep the API terminal open. In another terminal, run:

```powershell
Set-Location C:\OpsPilot\opspilot-cli
.\.venv\Scripts\python.exe -m scripts.cli
```

### Install and run on macOS/Linux

Extract the folder or ZIP to `/opt/opspilot-cli`, then run:

```sh
cd /opt/opspilot-cli
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

In a second terminal run `.venv/bin/python -m scripts.cli` from that package folder.

The CLI checks readiness, prompts for a password without echoing it, uses the API session cookie and CSRF token, then revokes the session on exit. It does not start the API. Select another API origin with `--url` or `OPSPILOT_URL`:

```powershell
.\.venv\Scripts\python.exe -m scripts.cli --url https://opspilot.example.com
```

Remote URLs require HTTPS; plain HTTP is allowed only for loopback. The API remains responsible for role checks and safety controls.

## Connect an existing service

OpsPilot is a separate incident service, not an agent library that automatically installs into or instruments an application. Supported inputs are:

1. **Alerts:** authenticated `POST /api/v1/webhooks/alerts`.
2. **Normalized evidence:** send with an alert or attach to a manual incident before its first investigation. Logs, traces, and change events use this push contract; they have no provider-specific readers.
3. **Prometheus:** configure the base URL and PromQL mappings to supported metric signal IDs. Queries are read-only and bounded by service scope and incident window.
4. **MCP:** run `python -m backend.mcp_server` as a trusted stdio child process to expose ten read-only, incident-scoped tools.

Map your service into OpsPilot's service registry, use actual event timestamps, choose supported signal IDs, and validate source mappings against known events. Unknown signals remain evidence but cannot match a deterministic diagnosis. Observation text and provenance are caller-provided and not independently verified.

## Incident workflow

1. Start a seeded replay, create a manual incident, or submit an authenticated alert.
2. Review service scope, dependencies, evidence timestamps/provenance, and unavailable tools.
3. Run the read-only investigation. It gathers bounded observations, checks deterministic signatures, and records findings, evidence, tool outcomes, and timeline. Insufficient or conflicting evidence stays inconclusive.
4. Review the report and evidence before deciding what to do.
5. For eligible seeded cases, an operator may request an allowlisted action. Proposal creation does not execute it.
6. The approver role reviews the exact parameters and approves or rejects with an audit note. An operator cannot approve a proposal.
7. An operator can execute an approved proposal once against the isolated simulator. The approver role cannot execute an action it approved. Server-recorded verification controls resolution.
8. Export the report, add audited notes, and back up incident/checkpoint data as needed.

Both CLI roles can view overview, incidents, reports, and notes. Operators can start replays, create incidents, investigate, propose actions, execute approved actions, and run seeded evaluations. Approvers can review and decide pending requests. For the guided demonstration, use `SCN-001` and switch credentials between the operator and approver roles.

## API and integrations

API base path: `/api/v1`. `GET /api/v1/health` is public; most other routes need a session cookie and CSRF token. The alert webhook uses a bearer token. See [API contracts](docs/api.md) for all routes and validation rules.

### Alert intake example

Set a random webhook token of at least 32 characters before starting the server:

```powershell
$env:OPSPILOT_ALERT_WEBHOOK_TOKEN = (.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
.\.venv\Scripts\python.exe app.py
```

Example request (replace service, event details, and correlation ID):

```powershell
$headers = @{
  Authorization = "Bearer $env:OPSPILOT_ALERT_WEBHOOK_TOKEN"
  "Content-Type" = "application/json"
}
$body = @{
  title = "Checkout database pool saturated"
  severity = "P1"
  service_id = "checkout"
  description = "Checkout cannot acquire a database connection."
  correlation_id = "alert-2026-10-11-001"
  evidence = @(@{
    kind = "metrics"
    service_id = "checkout"
    source = "checkout-pool-exporter"
    observation = "All configured database connections are in use."
    observed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    severity = "critical"
    signal_id = "metric.db_pool_saturated"
  })
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/api/v1/webhooks/alerts" -Headers $headers -Body $body
```

An incident accepts up to 25 records of kind `logs`, `metrics`, `traces`, or `changes`. Timestamps must be timezone-aware and within the prior seven days; observations are limited to 1,200 characters. Service/signal scope is checked. Exact retries with the same correlation ID deduplicate; reusing an ID with a different payload is rejected.

### Prometheus configuration

```powershell
$env:OPSPILOT_PROMETHEUS_URL = "https://prometheus.example.com"
$env:OPSPILOT_PROMETHEUS_QUERIES = '{"metric.db_pool_saturated":"checkout_db_pool_utilization{service_id=\"checkout\"} > 0.9"}'
$env:OPSPILOT_PROMETHEUS_TOKEN = "<read-only-token>"
.\.venv\Scripts\python.exe app.py
```

Each key must be a supported metric signal ID. Its expression must filter to that signal's registered service and return a series only when the condition is met. Limits: seven-day incident window, five seconds per query, 15 seconds total, one-megabyte response, and 25 samples per query. Validate expressions in Prometheus first. See the [operations runbook](docs/runbook.md).

### Local MCP server

For a trusted MCP client, run:

```powershell
.\.venv\Scripts\python.exe -m backend.mcp_server
```

It runs over local stdio, does not open a network listener, and exposes bounded read-only tools. Configure the client with the absolute Python path and repository/package working directory.

## Configuration

| Variable | Purpose |
| --- | --- |
| `OPSPILOT_DATA_DIR` | Incident DB and default checkpoint DB directory; defaults to `data/` beside `app.py`. |
| `OPSPILOT_HOST` / `OPSPILOT_PORT` | Listener address/port; defaults to `127.0.0.1` / `8765`. |
| `OPSPILOT_PASSWORD` / `OPSPILOT_APPROVER_PASSWORD` | Distinct credentials, at least 16 characters; random values print at startup if unset. |
| `OPSPILOT_URL` | CLI API origin; defaults to loopback. Remote origins must use HTTPS. |
| `OPSPILOT_ALERT_WEBHOOK_TOKEN` | Optional webhook bearer token, at least 32 characters. |
| `OPSPILOT_CHECKPOINT_DATABASE_URL` | Optional PostgreSQL URL for LangGraph checkpoints only; incidents remain in SQLite. |
| `OPSPILOT_PROMETHEUS_URL` | Optional Prometheus URL; HTTP only for loopback. |
| `OPSPILOT_PROMETHEUS_QUERIES` | JSON map of supported metric signal IDs to service-scoped PromQL. |
| `OPSPILOT_PROMETHEUS_TOKEN` | Optional Prometheus bearer token; use read-only access. |
| `OPSPILOT_ALLOW_REMOTE` | Set `true` for non-loopback; also needs configured credentials, HTTPS origin, and secure cookies. |
| `OPSPILOT_PUBLIC_ORIGIN` | Exact HTTPS origin behind a trusted TLS proxy. |
| `OPSPILOT_COOKIE_SECURE` | Set `true` when public origin uses HTTPS. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional OTLP HTTP endpoint for API traces and metrics. |
| `OPSPILOT_LLM_DATA_CONSENT` | Must be `true` before evidence can be sent to an external model. |
| `OPSPILOT_LLM_API_KEY` / `OPSPILOT_LLM_MODEL` / `OPSPILOT_LLM_BASE_URL` | Optional HTTPS OpenAI-compatible provider settings. |

## Development and verification

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall -q app.py backend scripts
node --check web\app.js
.\.venv\Scripts\python.exe -m scripts.evaluate
.\.venv\Scripts\python.exe -m scripts.package_cli --output "$env:TEMP\opspilot-cli-check"
```

The seeded evaluation checks signature consistency. A separate 17-case composition set checks decisions after signals have already been mapped. Neither establishes field accuracy on raw telemetry. Tests cover API behavior, evidence scope, authorization, approval, verification, checkpoint recovery, and backup/restore. CI runs the Python test/static checks, dependency audit, and container build. See [engineering audit](docs/engineering-audit.md) for scope and results.

With the server running, smoke-test the loopback health endpoint from another terminal:

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_load --requests 200 --concurrency 8
```

This is not a capacity test of investigations or external providers.

## Backup and restore

Back up incident data and checkpoints to a protected location:

```powershell
.\.venv\Scripts\python.exe scripts/backup.py --output-dir D:\OpsPilotBackups
```

Restore verifies the manifest, SHA-256 hashes, and SQLite integrity and refuses to overwrite an existing directory:

```powershell
.\.venv\Scripts\python.exe scripts/backup.py --restore-from "D:\OpsPilotBackups\<backup-folder>" --data-dir "D:\OpsPilotRestore\rehearsal-01"
$env:OPSPILOT_DATA_DIR = "D:\OpsPilotRestore\rehearsal-01"
.\.venv\Scripts\python.exe app.py
```

Check recovered incidents and checkpoints before routing operators to the restored directory. The databases are separate; this is not point-in-time recovery or automated failover. See the [runbook](docs/runbook.md).

## Architecture and scope

| Area | Implementation |
| --- | --- |
| Web UI | Static HTML, CSS, and JavaScript served by FastAPI. |
| API | FastAPI, Uvicorn, and Starlette; versioned JSON endpoints. |
| Incident/audit data | SQLite. |
| Workflow | LangGraph with SQLite checkpoints by default; optional PostgreSQL checkpoint store. |
| Diagnosis | Deterministic evidence-linked matching; optional model ranking only reorders supported candidates. |
| Evidence tools | Ten bounded MCP tools, normalized observations, optional Prometheus metrics. |
| Remediation | Typed allowlist, separate approver and operator roles, idempotent execution, server-side simulator verification. |
| Observability | Prometheus-format request metrics and optional OpenTelemetry OTLP export. |

The registry has eight services. The replay catalog has 36 deterministic cases: 28 supported labels and 8 expected-inconclusive cases. The separate 17-case evidence-composition set currently checks 13 supported decisions and 4 expected abstentions after signal mapping. These fixture results do not measure raw telemetry classification accuracy. Prometheus metrics and submitted observations can come from the operator-configured environment.

See [system architecture](docs/architecture.md), [security boundary](docs/security.md), and [API contracts](docs/api.md).

## Production deployment boundary

The container runs non-root, has a database readiness check, and can sit behind a trusted TLS reverse proxy. Remote binding requires explicit opt-in and secure configuration. This is not a turnkey multi-tenant hosted incident platform: it uses two shared role credentials, has no tenant/per-user authorization, stores incident records in SQLite, and executes only against the isolated simulator. Before connecting production workloads, add managed identity, tenant authorization, hosted storage/HA, and deployment-target testing, then complete an organization-specific security review. Never point the simulator action interface at a real service.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `py -3.11` not found | Install Python 3.11–3.14 and the launcher, or use an installed supported version with `python -m venv .venv`. |
| Port 8765 busy | Set `OPSPILOT_PORT` before starting and pass the same origin to CLI `--url`. |
| CLI cannot connect | Start `app.py` separately; check `GET http://127.0.0.1:8765/api/v1/health` returns `status: ok`. |
| Sign-in fails | Use the credential printed/configured for the current server role. Generated values change after restart. |
| Webhook returns 503 | Set `OPSPILOT_ALERT_WEBHOOK_TOKEN` to 32+ characters, then restart. |
| Webhook returns 409 | Correlation ID reused with different body; use original payload or a new ID. |
| Investigation inconclusive | Check signal IDs, timestamps, scope, conflicts, and unavailable-source results. Inconclusive findings cannot trigger actions. |
| Action cannot be proposed | Only eligible seeded simulator cases can create proposals. |
| Approval expired | Re-investigate and request a new proposal; approvals expire after 30 minutes. |
| PostgreSQL did not move incident data | PostgreSQL configures workflow checkpoints only; incidents remain in SQLite. |

## Repository layout

```text
app.py                  Incident, API, and persistence logic
backend/                ASGI adapter, investigation graph, evidence, integrations
web/                    Console, introduction, and captioned demo video
tests/                  Unit and API integration tests
scripts/                CLI, package builder, backup, evaluation, smoke utilities
docs/                   API, architecture, security, operations, audit material
.github/workflows/      Python verification, container build, tag release jobs
Dockerfile              Non-root container image
requirements.txt        Runtime dependencies
```
