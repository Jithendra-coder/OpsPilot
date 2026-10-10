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
    Exec[Allowlisted simulator executor]
    Obs[Prometheus and optional OTLP]
    Browser --> ASGI --> API --> DB
    API --> Graph --> Tools --> Lab
    Tools --> MCP
    Graph -. opt-in ranking .-> LLM
    API --> Exec --> Lab
    ASGI --> Obs
~~~

## Runtime boundaries

- FastAPI provides ASGI lifecycle, request limits, response security headers, the introduction at `/`, the console at `/console` (and legacy `/index.html`), static assets, range-capable demo media, and request telemetry. The versioned API currently dispatches through the existing synchronous handler for compatibility; it is not a set of independently layered FastAPI routers.
- SQLite is the source of truth for incidents, event and audit history, evidence, proposals, approvals, executions, and verification. Startup creates missing tables and records a versioned session-column upgrade. A general migration framework for future schema changes is not included. Use the online backup command before upgrades and protect the data directory.
- LangGraph persists workflow checkpoints in a separate local SQLite file by default. OPSPILOT_CHECKPOINT_DATABASE_URL changes only this checkpoint store to PostgreSQL; it does not migrate the incident store.
- Read tools and the stdio MCP gateway use one bounded, incident-scoped catalog. The catalog returns fixture observations, not live Loki, Prometheus, Tempo, or application data.
- The deterministic signature engine is the authority for supported causes. Its confidence value is a support score, not a calibrated probability. An optional model may reorder already-generated candidates and annotate missing evidence only.
- The action executor has no shell, network, deployment, or arbitrary parameter interface. It changes the state of an eligible seeded lab run in the operational database transaction, records verification, and resolves only after its server-owned checks pass.
- The browser uses static HTML, CSS, and JavaScript. Incident evidence and user-entered text are escaped before insertion into the DOM.

## Investigation sequence

The graph records intake and the authorized dependency scope, reads health/dependency metadata, then gathers logs, metrics, traces, deployment events, and configuration events. It deduplicates observations, evaluates competing signatures, and optionally asks a configured model to rank those fixed candidates. Tool failures remain explicit and force the deterministic diagnosis to stay inconclusive. The incident result, evidence, tool outcomes, and timeline are persisted before the API returns.

Completed request retries with the same incident/idempotency key reuse the stored result. Checkpoint data survives process restart. A failed investigation remains eligible for retry with its original idempotency key; validate recovery behavior against the target checkpoint backend before operating a hosted service.

## Persistence model

SQLite tables cover services, scenarios, incidents, incident events, comments, sessions, investigations, run events, evidence, alerts, lab runs, remediation proposals, approval requests, action executions, verification results, evaluations, and audit events. Unique keys protect alert correlation IDs, investigation idempotency keys, approval/proposal associations, and action execution keys. A SQLite trigger prevents changing approved proposal parameters.

The scenario catalog keeps expected fault labels out of investigator-facing list responses. Evaluation code has access to those labels and stores a reproducible report.

## Production deployment boundary

This architecture is appropriate for a controlled local portfolio lab. It has not been load-tested and does not implement tenant isolation, per-user identity, a PostgreSQL operational data layer, migration/restore automation, a real instrumented service environment, external observability adapters, or an independently deployed job queue. A reverse proxy can terminate TLS for a restricted deployment, but remote binding is an explicit opt-in and is not a claim of hosted-production readiness.
