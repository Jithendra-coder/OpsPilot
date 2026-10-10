# Architecture and data flow

~~~mermaid
flowchart LR
    Browser[Product introduction and local console]
    ASGI[FastAPI ASGI shell]
    API[Versioned incident API]
    DB[(SQLite operational store)]
    Graph[Checkpointed LangGraph]
    Tools[Scoped read-only tool catalog]
    MCP[Local stdio MCP]
    LLM[Optional HTTPS hypothesis ranking]
    Lab[Seeded local incident lab]
    Push[Operator or authenticated webhook evidence]
    Exec[Allowlisted simulator executor]
    Obs[Prometheus and optional OTLP]
    Browser --> ASGI --> API --> DB
    Push --> API
    API --> Graph --> Tools --> Lab
    Tools --> DB
    Tools --> MCP
    Graph -. opt-in ranking .-> LLM
    API --> Exec --> Lab
    ASGI --> Obs
~~~

## Runtime boundaries

- FastAPI provides ASGI lifecycle, request limits, response security headers, the introduction at `/`, the console at `/console` (and legacy `/index.html`), static assets, range-capable demo media, and request telemetry. The versioned API currently dispatches through the existing synchronous handler for compatibility; it is not a set of independently layered FastAPI routers.
- SQLite is the source of truth for incidents, event and audit history, submitted observations, investigation evidence, proposals, approvals, executions, and verification. Startup creates missing tables and applies versioned session and evidence-schema migrations. A general migration framework for future schema changes is not included. Use the online backup command before upgrades and protect the data directory.
- LangGraph persists workflow checkpoints in a separate local SQLite file by default. SQLite checkpoint schema setup is serialized on first use and each checkpoint connection has a 15-second busy timeout. OPSPILOT_CHECKPOINT_DATABASE_URL changes only this checkpoint store to PostgreSQL; it does not migrate the incident store.
- Read tools and the stdio MCP gateway use one bounded, incident-scoped catalog. It reads replay fixtures, normalized observations pushed through the authenticated incident API, or configured Prometheus metric queries; each tool response is capped at 50 records and submitted event times must be within seven days.
- The deterministic signature engine is the authority for supported causes. Its displayed heuristic support score is not a calibrated probability. Classification currently matches internal signal IDs from the bundled catalog. An optional model may reorder already-generated candidates and annotate missing evidence only.
- The action executor has no shell, network, deployment, or arbitrary parameter interface. It changes the state of an eligible seeded lab run in the operational database transaction, records verification, and resolves only after its server-owned checks pass.
- The browser uses static HTML, CSS, and JavaScript. Incident evidence and user-entered text are escaped before insertion into the DOM.

## Investigation sequence

The graph records intake and the authorized dependency scope, then gathers logs, metrics, traces, and change observations once. Its inputs come from a replay fixture, bounded normalized observations submitted by an operator or authenticated webhook, or explicitly configured Prometheus metric queries. Prometheus query expressions are operator-managed mappings to supported metric signal IDs and must filter to the service named by each signal and return data only when its condition is met. Requests use a five-second timeout with a 15-second aggregate query budget, cap response bodies at one megabyte, cap samples at 25 per query, and query no more than seven days. The fixture catalog does not separate deployment and configuration changes into distinct sources. The graph deduplicates observations, evaluates competing signatures, and optionally asks a configured model to rank those fixed candidates. Tool failures remain explicit and force the deterministic diagnosis to stay inconclusive. The incident result, evidence, tool outcomes, and timeline are persisted before the API returns.

Completed request retries with the same incident/idempotency key reuse the stored result. Checkpoint data survives process restart. A failed investigation remains eligible for retry with its original idempotency key; validate recovery behavior against the target checkpoint backend before operating a hosted service.

## Persistence model

SQLite tables cover services, scenarios, incidents, incident observations, incident events, comments, sessions, investigations, run events, evidence, alerts, lab runs, remediation proposals, approval requests, action executions, verification results, evaluations, and audit events. Unique keys protect alert correlation IDs, investigation idempotency keys, approval/proposal associations, and action execution keys. Evidence is stored per observation, including multiple records of the same kind in one run. A SQLite trigger prevents changing approved proposal parameters.

The scenario catalog keeps expected fault labels out of investigator-facing list responses. Its 36 seeded cases check rule consistency. A separate 17-case manual set measures cause selection and abstention after observations already have supported signal IDs; it does not measure raw-text classification, provider mapping quality, or field accuracy.

The backup command uses SQLite's online backup API. Restore verifies the manifest, checksums, and SQLite integrity before copying into a new directory, and refuses to overwrite an existing target. Restore is an operator-run action.

## Production deployment boundary

This architecture is appropriate for a controlled local portfolio lab. The optional Prometheus reader covers operator-configured metric queries; logs, traces, and change events still use the normalized push contract, and mapping correctness depends on operator-authored queries. The application has no tenant isolation or per-user identity, keeps operational records in SQLite, and acts only on the seeded simulator. The request path has not been capacity-tested against a deployment target. A reverse proxy can terminate TLS for a restricted deployment, but remote binding is an explicit opt-in and is not a claim of hosted-production readiness.
