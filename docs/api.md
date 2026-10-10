# HTTP API contract

Base path: /api/v1. JSON responses use an error envelope of {"error":{"code":"...","message":"..."}}. The FastAPI OpenAPI UI is intentionally disabled; this file is the checked-in route contract. Request objects reject unknown fields and are limited to 64 KiB.

## Authentication

Except health and the monitoring webhook, routes require a session cookie from POST /auth/session. Browser mutations require the returned X-CSRF-Token. The webhook uses its bearer token instead.

| Method and path | Authorization | Purpose |
| --- | --- | --- |
| GET /health | Public | Readiness check for the incident database. |
| POST /auth/session | Public | Body: password. Returns role and CSRF token, sets HTTP-only session cookie. |
| GET /auth/session | Session | Return current actor, role, and CSRF token. |
| DELETE /auth/session | Session + CSRF | Revoke the current session. |
| GET /overview | Session | Overview statistics, services, latest incidents, and activity. |
| GET /services | Session | Local registry and simulator health. |
| GET /scenarios | Session | Replay scenario metadata; expected labels are omitted. |
| GET /metrics | Session | Prometheus text metrics. |
| GET /incidents | Session | Search and filter incident list. Query: status, severity, q, limit (1–50), offset. |
| POST /incidents | Operator + CSRF | Create manual incident. Required: title, severity, service_id, description. Optional: owner, evidence. |
| POST /webhooks/alerts | Bearer token | Accept alert: title, severity, service_id, description, correlation_id; optional owner, evidence. Returns 201 for new, 200 for exact duplicate, 409 for same key/different payload. |
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
| POST /incidents/{id}/remediation/propose | Operator + CSRF | Create or reuse an eligible typed simulator proposal and independent approval request. |
| GET /approvals | Session | Approval history. Query status: pending, approved, rejected, expired, all. |
| POST /approvals/{id}/approve | Approver + CSRF | Body: decision note. Cannot approve own proposal. |
| POST /approvals/{id}/reject | Approver + CSRF | Body: decision note; rejected proposal returns incident to investigation. |
| POST /actions/{proposal_id}/execute | Different operator + CSRF | Body: idempotency_key. Executes the approved, unexpired catalog action only once in the isolated simulator. |
| GET /actions/{proposal_id-or-execution_id}/verification | Session | Server-recorded checks for the action. |
| POST /simulations/start | Operator + CSRF | Body: scenario_id and optional owner. Inject a seeded local fault. |
| POST /simulations/{incident_id}/reset | Operator + CSRF | Reset only before investigation or action history exists. |
| POST /evaluations | Operator + CSRF | Run all seeded signature consistency cases and persist the result. The report includes `evaluation_type` and a limitation note; `summary.accuracy` is the legacy field name for the seeded case match rate. |
| GET /evaluations | Session | Latest 20 saved evaluations. |

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

## Prometheus metrics reader

When `OPSPILOT_PROMETHEUS_URL` and `OPSPILOT_PROMETHEUS_QUERIES` are set, the investigation's metrics read executes each configured PromQL expression against the Prometheus range-query API. The JSON query map keys must be supported metric `signal_id` values. Expressions are trusted operator configuration and must filter to the corresponding registered service and return a series only when the signal condition is met. An optional `OPSPILOT_PROMETHEUS_TOKEN` is sent as a bearer token.

Requests are incident-window bounded to seven days, use a five-second per-request timeout and a 15-second total query budget, disable redirects, cap each response at one megabyte and 25 samples, and store no returned metric label values. Query results become evidence with `prometheus-http-api` provenance. A provider error is recorded as unavailable and prevents a supported diagnosis. The adapter does not verify that a query correctly represents its mapped failure signal. Logs, traces, and change events continue to use normalized evidence push intake.
