# Threat model and security boundary

## Protected assets

Incident descriptions, evidence, comments, session records, approval decisions, execution history, and audit events are stored under OPSPILOT_DATA_DIR. Local environment variables may contain login, webhook, PostgreSQL-checkpointer, OTLP, or model-provider credentials.

## Trust boundaries

| Input or component | Trust | Enforced handling |
| --- | --- | --- |
| Console session | Authenticated local operator or approver | Hashed random session token, HTTP-only SameSite cookie, eight-hour expiry, per-session CSRF token, same-origin check on login and mutations. |
| Monitoring webhook | External sender holding the configured bearer secret | Disabled without a 32-character token; strict JSON schema and field limits; at most 25 normalized observations; incident dependency and supported-signature scope checks; unique correlation ID; payload-hash conflict rejection. |
| Incident and telemetry text | Untrusted data | Bounded input, text-only rendering, no tool execution from content, candidate causes restricted to the deterministic catalog. |
| Investigation tools | Read-only, incident-scoped | Dependency-scope checks, bounded output, maximum seven-day query windows, typed errors; no arbitrary host or URL parameter. |
| Prometheus adapter | Read-only source configured by the operator | HTTPS or loopback HTTP only; bearer token is environment-only; redirects disabled; five-second timeout; one-megabyte response cap; supported metric signal IDs only; query window limited to seven days. Returned label values are not stored. |
| LLM provider | External service, disabled by default | Explicit consent switch, HTTPS-only URL, bounded evidence and response, heuristic secret redaction, no redirects; response can only rank existing candidates. |
| Remediation request | State-changing and privileged | Typed catalog action, eligible simulator only, immutable hashed parameters, approval by the separate approver role, short expiry, operator-role execution, server-owned verification. |
| MCP gateway | Local process user | stdio transport only and read tools only. Do not expose it through an unauthenticated network MCP endpoint. |

## Authentication and session notes

The current app has two shared local credentials with fixed roles, not an organization/user directory. Configure distinct random values of at least 16 characters using OPSPILOT_PASSWORD and OPSPILOT_APPROVER_PASSWORD. If omitted, the process prints random local credentials at startup. Password hashes use PBKDF2-HMAC-SHA256 with 600,000 iterations and process-local salts. Replacing configured passwords does not automatically revoke still-live database sessions; use the sign-out control, delete sessions during a planned maintenance window, or expire the data store when rotating credentials.

Login throttling reserves attempts atomically by client address, allows five attempts before a one-minute lock, expires inactive buckets, and caps in-memory address entries at 4,096. It is still process-local; high address churn can evict an older bucket. Run one app worker as configured. A multiworker or multi-replica deployment needs shared rate-limit state and a user identity provider before it is considered secure.

The remote-bind guard requires explicit opt-in, both configured credentials, an HTTPS public origin, and Secure cookies. Keep TLS termination on a trusted reverse proxy, keep the app listener private behind it, set the exact public origin, and verify proxy/header behavior. Do not expose the unauthenticated health route or local metrics endpoint beyond the intended network boundary.

## Data handling and limitations

Bundled replay observations are fixtures. The incident API can also accept caller-submitted observations; their text and provenance are not independently verified by OpsPilot. Prometheus query expressions and their service filters are operator-authored configuration; the adapter validates signal IDs and response shape, not whether an expression accurately represents its claimed failure. Keep the token read-only and target a trusted metrics endpoint. The LLM secret filter is a heuristic, not a data-loss-prevention system. If consent is enabled, bounded candidate descriptions and evidence observations may be sent to the configured provider, but novel secret formats may evade masking. Review source authorization and redaction before sending operational data to an external provider. Logs, traces, and change events have no provider-specific reader.

SQLite files and backups may contain sensitive incident data. Store them on access-controlled volumes, encrypt backup media outside the application, and rehearse restore. Backup files inherit the destination directory ACL; on POSIX the backup script also sets mode 0600.

## Required before shared or hosted production use

- Replace shared passwords with a managed identity provider, individual users, organization/service authorization, MFA, and revocation.
- Add organization boundaries in every query and background operation.
- Move operational records to a supported transactional database and introduce reviewed, versioned schema migrations.
- Use shared login rate limiting and request quotas; test CSRF, proxy trust, credential rotation, and session revocation.
- Add individual identity, source authorization, verified query mappings, and field-level redaction before using telemetry in a shared deployment.
- Keep execution isolated from production and independently review every allowlisted action.
- Add load, penetration, restore, failover, dependency-failure, and browser accessibility testing for the actual deployment.

Do not use this repository to restart, deploy, or modify a real service. The only executor target is an eligible local seeded simulation.
