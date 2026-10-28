# Threat model and security boundary

## Protected assets

Incident descriptions, evidence, comments, session records, approval decisions, execution history, and audit events are stored in SQLite by default or in the configured PostgreSQL database. Local environment variables may contain login, webhook, PostgreSQL, OTLP, or model-provider credentials.

## Trust boundaries

| Input or component | Trust | Enforced handling |
| --- | --- | --- |
| Console session | Authenticated local operator or approver account | Hashed random session token, HTTP-only SameSite cookie, eight-hour expiry, per-session CSRF token, same-origin check on login and mutations; named-account sessions are tied to an active user. |
| Monitoring webhook | External sender holding the configured bearer secret | Disabled without a 32-character token; normalized intake validates field limits and service/signature scope; Alertmanager intake accepts up to 25 alerts; correlation IDs deduplicate; payload-hash conflicts are rejected. |
| Incident and telemetry text | Untrusted data | Bounded input, text-only rendering, no tool execution from content, candidate causes restricted to the deterministic catalog. |
| Investigation tools | Read-only, incident-scoped | Dependency-scope checks, bounded output, maximum seven-day query windows, typed errors; no arbitrary host or URL parameter. |
| Observability adapters | Read-only Prometheus, Loki, and Tempo sources configured by the operator | HTTPS or loopback HTTP only; bearer token is environment-only; redirects disabled; bounded queries, response sizes, timeouts, service scope, and seven-day incident windows. Raw Loki lines and full Tempo spans are not stored. |
| LLM provider | External service, disabled by default | Explicit consent switch, HTTPS-only URL, bounded evidence and response, heuristic secret redaction, no redirects; response can only rank existing candidates. |
| Remediation request | State-changing and privileged | Typed catalog action, eligible simulator only, immutable hashed parameters, approval by the separate approver role, short expiry, operator-role execution, server-owned verification. |
| MCP gateway | Local process user | stdio transport only and read tools only. Do not expose it through an unauthenticated network MCP endpoint. |

## Authentication and session notes

For the local demo, two shared role passwords are used until the first named team account is added. Create named accounts with `python -m scripts.accounts`; each has a separate operator or approver role and a salted PBKDF2-HMAC-SHA256 password hash with 600,000 iterations. The account tool disables accounts and revokes their sessions. This is a local account store, not SSO or MFA. Login throttling is still process-local, so keep one application worker until shared rate-limit state is added.

Login throttling reserves attempts atomically by client address, allows five attempts before a one-minute lock, expires inactive buckets, and caps in-memory address entries at 4,096. It is still process-local; high address churn can evict an older bucket. Run one app worker as configured. A multiworker or multi-replica deployment needs shared rate-limit state and a user identity provider before it is considered secure.

The remote-bind guard requires explicit opt-in, both configured credentials, an HTTPS public origin, and Secure cookies. Keep TLS termination on a trusted reverse proxy, keep the app listener private behind it, set the exact public origin, and verify proxy/header behavior. Do not expose the unauthenticated health route or local metrics endpoint beyond the intended network boundary.

## Data handling and limitations

Bundled replay observations are fixtures. The incident API can also accept caller-submitted observations; their text and provenance are not independently verified by OpsPilot. Prometheus, Loki, and Tempo mappings are operator-authored configuration; the adapters validate signal IDs, scope, and response shape, not whether a mapping accurately represents its claimed failure. Keep credentials read-only and target trusted endpoints. The LLM secret filter is a heuristic, not a data-loss-prevention system. If consent is enabled, bounded candidate descriptions and evidence observations may be sent to the configured provider, but novel secret formats may evade masking. Review source authorization and redaction before sending operational data to an external provider. Changes can still use normalized evidence intake.

SQLite files and PostgreSQL backups may contain sensitive incident data. Store them on access-controlled volumes, encrypt backup media outside the application, and rehearse restore. The bundled backup script currently handles SQLite files; PostgreSQL deployments need protected `pg_dump` backups. SQLite backup files inherit the destination directory ACL; on POSIX the script also sets mode 0600.

## Required before shared or hosted production use

- Add SSO, MFA, tenant isolation, organization/service authorization, and externally managed identity lifecycle.
- Add organization boundaries in every query and background operation.
- Add a reviewed migration and data-migration process for existing SQLite installations before changing their `OPSPILOT_DATABASE_URL`.
- Use shared login rate limiting and request quotas; test CSRF, proxy trust, credential rotation, and session revocation.
- Add individual identity, source authorization, verified query mappings, and field-level redaction before using telemetry in a shared deployment.
- Keep execution isolated from production and independently review every allowlisted action.
- Add load, penetration, restore, failover, dependency-failure, and browser accessibility testing for the actual deployment.

Do not use this repository to restart, deploy, or modify a real service. The only executor target is an eligible local seeded simulation.
