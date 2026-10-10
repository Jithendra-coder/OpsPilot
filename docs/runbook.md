# Operator runbook

## Start and readiness

1. Install the package ranges from requirements.txt in a virtual environment.
2. Configure two unique credentials before any shared use. Keep generated credentials out of shell history and logs.
3. Start with python app.py and confirm GET /api/v1/health reports status ok and database ready.
4. Keep the listener on loopback for the local lab. Confirm the browser shows the local-environment indicator.
5. Start the MCP server only as a local stdio process for a trusted client; it reads the same local data store.

## Investigation and action

- A missing or unavailable source should lower confidence and keep the result inconclusive. Inspect tool errors and provenance before acting.
- Only supported findings on eligible seeded simulations can propose an action. Manual incidents and unknown scenarios cannot execute remediation.
- The proposal expires after 30 minutes. A fresh investigation and proposal are required after expiry or if the simulator state changes.
- The approver and executor must be different actors. Replaying the exact idempotency key returns the saved result. A different key cannot re-run that proposal.
- A failed post-action check leaves the incident unresolved. Escalate it and preserve the report; never edit the database to force resolution.

## Back up SQLite data

The backup utility uses SQLite's online backup API so it can read a database while the application is running, verifies each resulting database, records SHA-256 hashes, and includes the workflow checkpoint file when present. Choose a protected directory outside OPSPILOT_DATA_DIR.

~~~powershell
python scripts/backup.py --output-dir D:\OpsPilotBackups
~~~

The printed directory contains the database files and manifest.json. Protect and encrypt that directory using the host's backup controls. Before a restore, stop OpsPilot, compare each manifest hash with Get-FileHash, preserve the existing data directory, then copy the chosen database files into a new data directory and start the app against it. Rehearse restore with a disposable copy before treating backups as a recovery guarantee.

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

Incident records and workflow checkpoints are separate stores. Back up both together. A valid incident database backup without its corresponding checkpoint file preserves completed records but may not resume an in-flight graph. There is no built-in automated restore, point-in-time recovery, HA, or cross-replica locking.

## Operational limits

The included lab does not start or instrument real microservice containers. Logs, metrics, traces, deployment and configuration records are scenario fixtures. Health checks reflect local simulator state. Use the replay scenarios for deterministic behavior and never connect the action interface to a real target.
