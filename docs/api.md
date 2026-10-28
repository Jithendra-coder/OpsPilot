# HTTP API contract

Base path: /api/v1. JSON responses use an error envelope of {"error":{"code":"...","message":"..."}}. The FastAPI OpenAPI UI is intentionally disabled; this file is the checked-in route contract. Request objects reject unknown fields and are limited to 64 KiB.

## Authentication

Except health and the monitoring webhook, routes require a session cookie from POST /auth/session. Browser mutations require the returned X-CSRF-Token. The webhook uses its bearer token instead.

| Method and path | Authorization | Purpose |
| --- | --- | --- |
| GET /health | Public | Readiness check for the incident database. |
| POST /auth/session | Public | Body: password and optional username. Username becomes required after named team accounts are configured. Returns account/role and CSRF token, sets HTTP-only session cookie. |
| GET /auth/session | Session | Return current actor, role, and CSRF token. |
| DELETE /auth/session | Session + CSRF | Revoke the current session. |
| GET /overview | Session | Overview statistics, services, latest incidents, and activity. |
| GET /services | Session | Local registry and simulator health. |
| GET /scenarios | Session | Replay scenario metadata; expected labels are omitted. |
| GET /metrics | Session | Prometheus text metrics. |
| GET /incidents | Session | Search and filter incident list. Query: status, severity, q, limit (1–50), offset. |
| POST /incidents | Operator + CSRF | Create manual incident. Required: title, severity, service_id, description. Optional: owner, evidence. |
| POST /webhooks/alerts | Bearer token | Accept normalized alert: title, severity, service_id, description, correlation_id; optional owner, evidence. Returns 201 for new, 200 for exact duplicate, 409 for same key/different payload. |
| POST /webhooks/alertmanager | Bearer token | Accept an Alertmanager webhook group of up to 25 firing/resolved alerts. Firing alerts create or deduplicate incidents; resolved notifications add a review event and never close the OpsPilot incident. |
| GET /incidents/{id} | Session | Incident and latest investigation summary. |
| GET /incidents/{id}/report | Session | Evidence, finding, remediation history, timeline, notes, and verification. |
| GET /incidents/{id}/investigations | Session | Latest 50 investigation runs. |
| GET /incidents/{id}/events | Session | Incident events and operator comments. |
| GET /incidents/{id}/evidence | Session | Evidence attached to the incident. |
| POST /incidents/{id}/evidence | Operator + CSRF | Attach normalized observations before the first investigation. Only manual and authenticated webhook incidents accept additions. |
| GET /incidents/{id}/hypotheses | Session | Latest run's candidate hypotheses. |
| POST /incidents/{id}/investigate | Operator + CSRF | Body: idempotency_key (8–128 characters). Runs bounded read-only investigation. |
| POST /incidents/{id}/comments | Operator or approver + CSRF | Body: body (1–1200 characters). Adds an audited note. |
| POST /incidents/{id}/status | Operator + CSRF | Body: status and note. Controlled remediation, verification, and resolution states cannot be caller-set. |
| GET /investigations/{id}/status | Session | Current persisted investigation state and result. |
| GET /investigations/{id}/events | Session | Tool and graph stage outcomes. |
| GET /investigations/{id}/evidence | Session | Evidence for a specific run. |
| GET /investigations/{id}/hypotheses | Session | Hypotheses for a specific run. |
| POST /incidents/{id}/remediation/propose | Operator + CSRF | Create or reuse an eligible typed simulator proposal for approver-role review. |
| GET /approvals | Session | Approval history. Query status: pending, approved, rejected, expired, all. |
| POST /approvals/{id}/approve | Approver + CSRF | Body: decision note. Cannot approve own proposal. |
| POST /approvals/{id}/reject | Approver + CSRF | Body: decision note; rejected proposal returns incident to investigation. |
| POST /actions/{proposal_id}/execute | Operator role + CSRF | Body: idempotency_key. Executes the approved, unexpired catalog action only once in the isolated simulator; the approver role that approved it cannot execute it. |
| GET /actions/{proposal_id-or-execution_id}/verification | Session | Server-recorded checks for the action. |
| POST /simulations/start | Operator + CSRF | Body: scenario_id and optional owner. Inject a seeded local fault. |
| POST /simulations/{incident_id}/reset | Operator + CSRF | Reset only before investigation or action history exists. |
| POST /evaluations | Operator + CSRF | Run all seeded signature consistency cases and persist the result. The report includes `evaluation_type` and a limitation note; `summary.accuracy` is the legacy field name for the seeded case match rate. |
| GET /evaluations | Session | Latest 20 saved evaluations. |

Named accounts are managed from a trusted application host with `python -m scripts.accounts add|set-password|disable|list`. The application does not expose account administration through its public API. Passwords are salted PBKDF2-HMAC-SHA256 hashes; disabling an account revokes its sessions. Before the first named account is added, the local operator and approver environment passwords remain available for the guided demo.

## Lifecycle rules

~~~text
NEW -> TRIAGING -> INVESTIGATING -> AWAITING_APPROVAL -> REMEDIATING -> VERIFYING -> RESOLVED
Any active state may be escalated or failed where the state machine permits it.
Approval rejection returns AWAITING_APPROVAL to INVESTIGATING.
RESOLVED and FAILED are terminal.
~~~

The executor derives action type and parameters from the allowlist. Approval is bound to the proposal hash and expires after 30 minutes. Expired approvals are reported as expired without changing data during a GET; an attempted late decision/execution records expiry, and an operator can start a new investigation from the expired request. Resolution is written only after the executor stores a passing verification result; user-supplied booleans do not count as verification.

## Normalized evidence input

`evidence` is optional on incident creation and alert intake. The attach route accepts the same object. An incident may contain at most 25 submitted records total; exact observation retries are deduplicated. Each record requires `kind`, `service_id`, `source`, `observation`, and timezone-aware ISO-8601 `observed_at`. Allowed kinds are `logs`, `metrics`, `traces`, and `changes`. `severity` is optional (`critical`, `error`, `warning`, `neutral`, or `info`); `signal_id` is optional and must be a supported signature for that evidence kind. Each observation is limited to 1,200 characters, source to 120, and event time to the prior seven days. Service and signature scope are checked against the incident's registered dependency graph. The normal 64 KiB request limit applies.

Example record:

~~~json
{
  "kind": "metrics",
  "service_id": "checkout",
  "source": "checkout-pool-exporter",
  "observation": "All configured database connections are in use.",
  "observed_at": "2026-10-10T12:00:00Z",
  "severity": "critical",
  "signal_id": "metric.db_pool_saturated"
}
~~~

Replace `observed_at` with the source event's actual recent timestamp.

Text without a recognized `signal_id` remains evidence, but cannot by itself match a root-cause signature. Insufficient or conflicting observations produce an inconclusive result. Evidence is immutable after the first investigation; create a new incident to investigate a changed evidence set. All caller-submitted text remains untrusted, and enabling external model review can transmit bounded evidence after explicit consent.

## Alertmanager webhook

Send Alertmanager's standard webhook body to `POST /api/v1/webhooks/alertmanager` with `Authorization: Bearer $OPSPILOT_ALERT_WEBHOOK_TOKEN`. The request uses the normal 64 KiB JSON body limit. Each alert requires a `fingerprint`, timezone-aware `startsAt`, a `service_id` label that exists in the registry, and `firing` or `resolved` status. Firing severity maps from `critical`, `error`, `warning`, `info`, or `debug` to OpsPilot P1–P4; the title comes from the summary annotation, then alertname. The alert fingerprint and start timestamp form a stable idempotency key.

Firing notifications create incidents at the alert's start time; exact repeats deduplicate. Resolved notifications append an audited `alert.source_resolved` event when the matching firing alert is known. This records the source's state for an operator to review; it does not transition or resolve the OpsPilot incident. Unknown service IDs and malformed timestamps are rejected. Configure `send_resolved: true` in Alertmanager if the operator should receive these updates.

## Prometheus metrics reader

When `OPSPILOT_PROMETHEUS_URL` and `OPSPILOT_PROMETHEUS_QUERIES` are set, the investigation's metrics read executes each configured PromQL expression against the Prometheus range-query API. The JSON query map keys must be supported metric `signal_id` values. Expressions are trusted operator configuration and must filter to the corresponding registered service and return a series only when the signal condition is met. An optional `OPSPILOT_PROMETHEUS_TOKEN` is sent as a bearer token.

Requests include at most one minute before the alert timestamp to account for alert evaluation delay, are capped to a seven-day window, use a five-second per-request timeout and a 15-second total query budget, disable redirects, cap each response at one megabyte and 25 samples, and store no returned metric label values. Query results become evidence with `prometheus-http-api` provenance. A provider error is recorded as unavailable and prevents a supported diagnosis. The adapter does not verify that a query correctly represents its mapped failure signal.

## Loki log reader

Set `OPSPILOT_LOKI_URL` to an HTTPS Loki base URL (HTTP is accepted only for loopback), and set `OPSPILOT_LOKI_QUERIES` to a JSON object mapping supported log signal IDs to literal substrings. For example:

~~~powershell
$env:OPSPILOT_LOKI_URL = "https://loki.example"
$env:OPSPILOT_LOKI_QUERIES = '{"log.db_acquire_timeout":"Connection acquisition timed out"}'
$env:OPSPILOT_LOKI_TOKEN = "<read-only bearer token>"
~~~

OpsPilot builds LogQL with a fixed `{service_name="<registered service id>"}` selector and the configured literal substring filter. It includes at most one minute before the alert timestamp to account for alert evaluation delay, caps the query window at seven days, requests no more than 25 entries per query and 50 records per tool, disables redirects and environment proxy settings, caps each response at one megabyte, and allows five seconds per request and 15 seconds per provider call. It stores a generic signal observation and timestamp, not raw log lines. Check that the configured service ID matches the `service_name` label in Loki and that each substring accurately represents its signal.

## Tempo trace reader

Set `OPSPILOT_TEMPO_URL` to an HTTPS Tempo base URL (HTTP is accepted only for loopback), and set `OPSPILOT_TEMPO_QUERIES` to a JSON object mapping supported trace signal IDs to a single attribute equality or inequality. For example:

~~~powershell
$env:OPSPILOT_TEMPO_URL = "https://tempo.example"
$env:OPSPILOT_TEMPO_QUERIES = '{"trace.db_wait_high":"span.http.response.status_code = 500"}'
$env:OPSPILOT_TEMPO_TOKEN = "<read-only bearer token>"
~~~

OpsPilot combines each configured condition with a fixed `resource.service.name` selector, includes at most one minute before the alert timestamp to account for alert evaluation delay, caps the search window at seven days, requests no more than 25 traces per query and 50 records per tool, and applies the same redirect, proxy, response-size, and timeout limits as the Loki reader. Evidence retains the trace ID, timestamp, duration, mapped signal, and provenance; it does not copy full spans. Validate service and attribute mappings against the source before enabling them.
