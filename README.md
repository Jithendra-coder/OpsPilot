# OpsPilot

OpsPilot is a local incident investigation and controlled-remediation platform. It combines an auditable incident workspace, a checkpointed LangGraph investigation, bounded read-only MCP tools, an evidence-linked diagnosis engine, a two-person approval flow, and an isolated fault replay lab.

## What works today

- Incident intake from the console, versioned API, or an authenticated alert webhook.
- Incident lifecycle, comments, evidence, investigation history, audit timeline, and JSON report export.
- Eight registered services and 36 deterministic cases, including missing, contradictory, multi-fault, and instruction-like evidence.
- A LangGraph workflow with a durable SQLite checkpointer; a PostgreSQL checkpointer can be configured independently.
- Ten bounded, read-only observability MCP tools over local scenario evidence.
- Optional, HTTPS-only OpenAI-compatible hypothesis ranking. It is disabled unless data transfer is explicitly enabled, and it cannot select an unsupported cause or execute an action.
- Immutable, typed remediation proposals for eligible seeded faults. A distinct approver must approve the exact parameters; a different operator executes the action against the simulator; server-side checks determine whether the incident can resolve.
- Request metrics, optional OTLP traces and metrics, and a verified SQLite backup utility.
- A minimal responsive console for overview, incidents, service topology, investigation, approvals, and replay/evaluation.

## Run locally

Requirements: Python 3.10 or newer and Node.js 20 or newer for the JavaScript syntax check. The API and console are served together.

~~~powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
~~~

Open http://127.0.0.1:8765 for the OpsPilot introduction. Choose **Get started** to open the authenticated console at http://127.0.0.1:8765/console. The console remains directly available at `/index.html` for existing bookmarks. On first start, the terminal prints separate one-time operator and approver passwords if they are not configured. Keep the terminal open until both values have been copied. These generated credentials change on the next process start; existing sessions expire after eight hours.

The introduction includes the local, captioned demo at `/demo.webm`. It uses a synthetic seeded scenario; it does not show or claim access to production telemetry.

For repeatable local credentials, set two different random values before starting. Keep them out of source control and logs.

~~~powershell
$env:OPSPILOT_PASSWORD = (python -c "import secrets; print(secrets.token_urlsafe(32))")
$env:OPSPILOT_APPROVER_PASSWORD = (python -c "import secrets; print(secrets.token_urlsafe(32))")
python app.py
~~~

By default, durable incident data is in data/opspilot.db and workflow checkpoints are in data/workflow-checkpoints.sqlite. Set OPSPILOT_DATA_DIR to move both local stores. The service listens on 127.0.0.1:8765 by default.

## Verify the main flow

1. Sign in as operator and start the database-pool replay.
2. Investigate; inspect the findings, evidence links, tool outcomes, and timeline.
3. Propose the allowlisted action. Sign in separately as approver, review the exact parameters, and approve or reject it with an audit note.
4. Sign in as a different operator, execute the approved action once, and confirm that server-recorded checks control resolution.
5. Run the complete 36-case evaluation. The checked-in benchmark test expects all 28 labelled cases to match and all 8 unlabeled cases to remain inconclusive.
6. Use the other fixtures to inspect missing-source, unavailable-tool, conflict, multi-fault, and untrusted-log behavior.

## Development checks

~~~powershell
python -m unittest discover -s tests
python -m py_compile app.py backend\*.py scripts\*.py
node --check web\app.js
~~~

The test suite covers the seeded diagnosis benchmark, alert authentication and deduplication, service scope and time bounds, MCP tool boundaries, optional-LLM consent/redaction and candidate limits, independent approval, immutable proposals, server-side verification, idempotent execution, checkpoint recovery, schema upgrade, and online backup integrity. It is not a load, penetration, browser-automation, or disaster-recovery certification.

## Settings

| Variable | Purpose |
| --- | --- |
| OPSPILOT_DATA_DIR | Directory for the incident database and default LangGraph checkpoint database. |
| OPSPILOT_HOST / OPSPILOT_PORT | Listener address and port. Defaults to 127.0.0.1 / 8765. |
| OPSPILOT_PASSWORD / OPSPILOT_APPROVER_PASSWORD | Distinct operator and approver credentials, at least 16 characters each. If absent, random values are printed at startup. |
| OPSPILOT_ALERT_WEBHOOK_TOKEN | Optional bearer credential for alert intake; must be at least 32 characters. |
| OPSPILOT_CHECKPOINT_DATABASE_URL | Optional PostgreSQL URL for LangGraph checkpoints only. Incident and approval records remain in SQLite. |
| OTEL_EXPORTER_OTLP_ENDPOINT | Optional OTLP HTTP endpoint for workflow API traces and metrics. |
| OPSPILOT_LLM_DATA_CONSENT | Must equal true before evidence observations can be sent to an external model provider. |
| OPSPILOT_LLM_API_KEY / OPSPILOT_LLM_MODEL / OPSPILOT_LLM_BASE_URL | Optional provider configuration. The base URL must use HTTPS. |

Alert intake is POST /api/v1/webhooks/alerts with an Authorization: Bearer header. Repeated correlation IDs are deduplicated; a reused ID with a different payload is rejected.

See [API contracts](docs/api.md), [architecture](docs/architecture.md), [security boundary](docs/security.md), and the [operations runbook](docs/runbook.md).

## Deployment boundary

This repository is a production-oriented, controlled local lab—not a hosted multi-tenant incident service. Its evidence sources are seeded fixtures; its primary operational store is SQLite; local accounts are two configured shared credentials; and remediation changes only simulator state. No live application telemetry adapters, organization membership model, external identity provider, PostgreSQL incident store, Docker Compose microservice stack, or performance/SLO certification is included. Do not connect it to production targets or claim high availability. The security and architecture docs identify the work required before shared or hosted use.
