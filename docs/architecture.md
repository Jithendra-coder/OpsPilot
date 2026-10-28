# Architecture and data flow

~~~mermaid
flowchart LR
    Browser[Product introduction and local console]
    ASGI[FastAPI ASGI shell]
    API[Versioned incident API]
    DB[(SQLite or PostgreSQL operational store)]
    Graph[Checkpointed LangGraph]
    Tools[Scoped read-only tool catalog]
    MCP[Local stdio MCP]
    LLM[Optional HTTPS hypothesis ranking]
    Lab[Seeded local incident lab]
    Demo[Instrumented checkout Compose demo]
    Push[Operator or authenticated alert/evidence webhook]
    Exec[Allowlisted simulator executor]
    Obs[Prometheus · Loki · Tempo · OTLP]
    Browser --> ASGI --> API --> DB
    Push --> API
    API --> Graph --> Tools --> Lab
    Demo --> Prometheus --> Push
    Demo --> OTEL[OTel Collector] --> Loki
    OTEL --> Tempo
    Tools --> Prometheus
    Tools --> Loki
    Tools --> Tempo
    Tools --> DB
    Tools --> MCP
    Graph -. opt-in ranking .-> LLM
    API --> Exec --> Lab
    ASGI --> Obs
~~~

## Runtime boundaries

- FastAPI provides ASGI lifecycle, request limits, response security headers, the introduction at `/`, the console at `/console` (and legacy `/index.html`), static assets, range-capable demo media, and request telemetry. The versioned API currently dispatches through the existing synchronous handler for compatibility; it is not a set of independently layered FastAPI routers.
- SQLite remains the default local store. Setting `OPSPILOT_DATABASE_URL` moves operational data to PostgreSQL; the adapter uses the same parameterized queries and database-enforced proposal immutability. Startup serializes PostgreSQL schema initialization with an advisory transaction lock. The SQLite path retains versioned migrations; a general migration framework for future schema changes is not included.
- LangGraph checkpoints use the operational PostgreSQL URL when configured, or a local SQLite file by default. `OPSPILOT_CHECKPOINT_DATABASE_URL` can override the checkpoint location. PostgreSQL schema initialization uses the same advisory lock so concurrent ASGI startup does not race its DDL.
- Read tools and the stdio MCP gateway use one bounded, incident-scoped catalog. It reads replay fixtures, normalized observations pushed through the authenticated incident API, or configured read-only Prometheus, Loki, and Tempo queries. Provider results are bounded by service scope, incident window, request count, response size, and time budget; raw Loki log lines and full Tempo spans are not persisted.
- The deterministic signature engine is the authority for supported causes. Its displayed heuristic support score is not a calibrated probability. Classification currently matches internal signal IDs from the bundled catalog. An optional model may reorder already-generated candidates and annotate missing evidence only.
- The action executor has no shell, network, deployment, or arbitrary parameter interface. It changes the state of an eligible seeded lab run in the operational database transaction, records verification, and resolves only after its server-owned checks pass.
- The optional Compose demo starts a separate checkout service that emits Prometheus metrics and OTLP logs/traces. Prometheus sends alerts through Alertmanager; the three source adapters read bounded observations into OpsPilot. This is live telemetry inside the isolated demo network, not instrumentation or control of an external user's service.
- The browser uses static HTML, CSS, and JavaScript. Incident evidence and user-entered text are escaped before insertion into the DOM.

## Investigation sequence

Alertmanager firing messages and normalized webhook alerts enter through bearer-token authentication. Alertmanager fingerprints and start times provide stable deduplication keys. Resolved source notifications are audited for operator review and do not automatically resolve an OpsPilot incident. The graph records intake and authorized dependency scope, then gathers logs, metrics, traces, and change observations once. Inputs come from replay fixtures, bounded normalized observations submitted by an operator or authenticated webhook, or explicitly configured Prometheus, Loki, and Tempo query mappings. Each provider mapping is an operator-owned assertion from a source query to a supported signal ID; correctness must be validated against the source. Provider readers include a one-minute pre-alert lookback for alert evaluation delay, then enforce the seven-day window, service scope, five-second request timeout, 15-second aggregate budget, one-megabyte response cap, and per-query result limits. Loki lines and full Tempo spans are not copied into incident storage. The fixture catalog does not separate deployment and configuration changes into distinct sources; an unconfigured change feed is treated as absent optional evidence, while a configured provider failure remains an explicit tool error and makes the diagnosis inconclusive. The graph deduplicates observations, evaluates competing signatures, and optionally asks a configured model to rank those fixed candidates. The incident result, evidence, tool outcomes, and timeline are persisted before the API returns.

Completed request retries with the same incident/idempotency key reuse the stored result. Checkpoint data survives process restart. A failed investigation remains eligible for retry with its original idempotency key; validate recovery behavior against the target checkpoint backend before operating a hosted service.

## Persistence model

The operational schema covers services, scenarios, incidents, incident observations, incident events, comments, users, sessions, investigations, run events, evidence, alerts, lab runs, remediation proposals, approval requests, action executions, verification results, evaluations, and audit events. Unique keys protect alert correlation IDs, investigation idempotency keys, approval/proposal associations, and action execution keys. Evidence is stored per observation, including multiple records of the same kind in one run. A database trigger prevents changing approved proposal parameters in both SQLite and PostgreSQL.

The scenario catalog keeps expected fault labels out of investigator-facing list responses. Its 36 seeded cases check rule consistency. A separate 17-case manual set measures cause selection and abstention after observations already have supported signal IDs; it does not measure raw-text classification, provider mapping quality, or field accuracy.

The backup command uses SQLite's online backup API. Restore verifies the manifest, checksums, and SQLite integrity before copying into a new directory, and refuses to overwrite an existing target. Restore is an operator-run action.

## Production deployment boundary

This architecture is appropriate for a controlled portfolio lab. Prometheus, Loki, and Tempo readers use operator-configured mappings; signal quality depends on validating those mappings against the source. Named local operator and approver accounts are supported, but there is no SSO, MFA, or tenant isolation. SQLite remains the local default; PostgreSQL is available for operational data and checkpoints. The action executor still targets only the seeded simulator. The request path has not been capacity-tested against a deployment target, so this is not a claim of hosted-production readiness.
