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
| POST /incidents | Operator + CSRF | Create manual incident. Required: title, severity, service_id, description. Optional: owner. |
| POST /webhooks/alerts | Bearer token | Accept alert: title, severity, service_id, description, correlation_id; optional owner. Returns 201 for new, 200 for exact duplicate, 409 for same key/different payload. |
| GET /incidents/{id} | Session | Incident and latest investigation summary. |
| GET /incidents/{id}/report | Session | Evidence, finding, remediation history, timeline, notes, and verification. |
| GET /incidents/{id}/investigations | Session | Latest 50 investigation runs. |
| GET /incidents/{id}/events | Session | Incident events and operator comments. |
| GET /incidents/{id}/evidence | Session | Evidence attached to the incident. |
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
| POST /evaluations | Operator + CSRF | Run all seeded diagnosis cases and persist the result. |
| GET /evaluations | Session | Latest 20 saved evaluations. |

## Lifecycle rules

~~~text
NEW -> TRIAGING -> INVESTIGATING -> AWAITING_APPROVAL -> REMEDIATING -> VERIFYING -> RESOLVED
Any active state may be escalated or failed where the state machine permits it.
Approval rejection returns AWAITING_APPROVAL to INVESTIGATING.
RESOLVED and FAILED are terminal.
~~~

The executor derives action type and parameters from the allowlist. Approval is bound to the proposal hash and expires after 30 minutes. Expired approvals are reported as expired without changing data during a GET; an attempted late decision/execution records expiry, and an operator can start a new investigation from the expired request. Resolution is written only after the executor stores a passing verification result; user-supplied booleans do not count as verification.
