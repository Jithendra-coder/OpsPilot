# Operator runbook

## Start and readiness

1. Install the package ranges from requirements.txt in a virtual environment.
2. Configure two unique credentials before any shared use. Keep generated credentials out of shell history and logs.
3. Start with python app.py and confirm GET /api/v1/health reports status ok and database ready.
4. Keep the listener on loopback for the local lab. Confirm the browser shows the local-environment indicator.
5. Start the MCP server only as a local stdio process for a trusted client; it reads the same local data store.

## Run the container behind TLS

Build the image with `docker build -t opspilot:local .`. The image runs as UID 10001, stores both databases under `/data`, and reports readiness through its container healthcheck. A non-loopback listener is guarded by the same explicit opt-in as the Python launch. Keep a protected environment file outside source control with distinct operator and approver passwords, `OPSPILOT_ALLOW_REMOTE=true`, `OPSPILOT_PUBLIC_ORIGIN=https://ops.example.com`, and `OPSPILOT_COOKIE_SECURE=true`. Replace the example origin with the exact HTTPS origin.

~~~sh
docker run --detach --name opspilot --restart unless-stopped \
  --publish 127.0.0.1:8765:8765 \
  --volume opspilot-data:/data \
  --env-file /etc/opspilot/opspilot.env \
  ghcr.io/owner/opspilot:v1.0.0
~~~

Replace the sample image path and tag with the published image. Terminate TLS at a trusted reverse proxy on the host and proxy to `127.0.0.1:8765`. Use a protected secret store for the environment file and restrict access to the Docker socket and data volume. GitHub Actions runs the Python tests and static checks before the pull-request image build or version-tag GHCR publication. Restore into a separate volume and change the deployment's data mount only after verifying recovered incident history and checkpoint status.

## Connect Prometheus metrics

Set `OPSPILOT_PROMETHEUS_URL` to an HTTPS Prometheus base URL (HTTP is accepted only for loopback), and set `OPSPILOT_PROMETHEUS_QUERIES` to a JSON object mapping supported metric signal IDs to PromQL expressions. Expressions must scope to the signal's registered service and filter to the condition that should count as evidence. For example, adapt the metric name and labels to the source before using:

~~~powershell
$env:OPSPILOT_PROMETHEUS_URL = "https://prometheus.example"
$env:OPSPILOT_PROMETHEUS_QUERIES = '{"metric.db_pool_saturated":"checkout_db_pool_utilization{service_id=\"checkout\"} > 0.9"}'
$env:OPSPILOT_PROMETHEUS_TOKEN = "<read-only bearer token>"
~~~

The reader sends incident-window range queries with redirects disabled, a five-second per-request timeout, a 15-second total query budget, a one-megabyte response limit, at most 25 samples per query, and a maximum seven-day window. It records no returned label values. An empty query result means no matching evidence; a source error is recorded as unavailable and prevents a supported diagnosis. Test every configured expression against the provider's own query UI before enabling it. Logs, traces, and change records continue to use the normalized evidence intake contract.

## Investigation and action

- A missing or unavailable source should lower confidence and keep the result inconclusive. Inspect tool errors and provenance before acting.
- Only supported findings on eligible seeded simulations can propose an action. Manual incidents and unknown scenarios cannot execute remediation.
- The proposal expires after 30 minutes. A fresh investigation and proposal are required after expiry or if the simulator state changes.
- The approver-role account cannot execute the proposal it approved. An operator-role account may execute it once. Replaying the exact idempotency key returns the saved result; a different key cannot re-run that proposal.
- A failed post-action check leaves the incident unresolved. Escalate it and preserve the report; never edit the database to force resolution.

## Back up SQLite data

The backup utility uses SQLite's online backup API so it can read a database while the application is running, verifies each resulting database, records SHA-256 hashes, and includes the workflow checkpoint file when present. Choose a protected directory outside OPSPILOT_DATA_DIR.

~~~powershell
python scripts/backup.py --output-dir D:\OpsPilotBackups
~~~

The printed directory contains the database files and manifest.json. Protect and encrypt that directory using the host's backup controls. Restore validates the manifest, SHA-256 hashes, and SQLite integrity, and refuses to overwrite an existing directory. Rehearse with a new disposable path:

~~~powershell
python scripts/backup.py --restore-from "D:\OpsPilotBackups\opspilot-20261010T120000000000Z" --data-dir "D:\OpsPilotRestore\rehearsal-01"
$env:OPSPILOT_DATA_DIR = "D:\OpsPilotRestore\rehearsal-01"
python app.py
~~~

Replace the example backup directory with the exact folder printed by the backup command.

Check the restored incident history and investigation status before switching any operator to that data directory. The backup is a point-in-time copy of each database, not a coordinated transaction across the incident and checkpoint stores; rehearse recovery before treating it as a recovery guarantee.

## Common failures

| Symptom | Response |
| --- | --- |
| Sign-in fails after restart | Use the currently printed or configured role credential. Generated credentials rotate each start. Live sessions are stored until expiry and are not revoked just by changing the password. |
| Webhook returns 503 | Set OPSPILOT_ALERT_WEBHOOK_TOKEN to a random value at least 32 characters long, then restart. |
| Webhook returns 409 | A correlation ID was reused with a different payload. Send the same event body or use a new source correlation ID. |
| Investigation returns an error | Check server logs and GET /investigations/{id}/status. Retry with the original idempotency key. Checkpoint recovery has not been certified across every backend failure mode. |
| Proposal is unavailable | Confirm investigation is supported, the incident is an eligible seeded simulation, and the original fault is still active. Inconclusive evidence is intentionally non-actionable. |
| Approval expired or simulator changed | Preserve the report, run a new investigation, and request a new approval. Do not edit the immutable action record. |
| OTLP export is unavailable | Remove OTEL_EXPORTER_OTLP_ENDPOINT to disable export, or restore the configured collector. Local request metrics remain available to an authenticated session. |
| LLM review is unavailable | The deterministic ranking remains authoritative; provider timeouts or invalid output fall back without blocking investigation. |

## Recovery and incident data

Incident records and workflow checkpoints are separate stores. Back up both together. A valid incident database backup without its corresponding checkpoint file preserves completed records but may not resume an in-flight graph. Restore is a local command, not an automated failover or point-in-time recovery service. HA and cross-replica locking are not provided.

## Operational limits

The included lab does not start or instrument real microservice containers. Logs, metrics, traces, deployment and configuration records are scenario fixtures. Health checks reflect local simulator state. Use the replay scenarios for deterministic behavior and never connect the action interface to a real target.
