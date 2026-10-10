# OpsPilot portfolio diagrams

These diagrams describe the implementation in this repository. The SVG files are the editable, hand-laid-out vector masters. The Mermaid files preserve the same component and flow relationships in a diagram-as-code form. PNGs are high-resolution exports rendered from the SVG masters.

## Files

| Diagram | SVG | PNG | Editable flow source |
| --- | --- | --- | --- |
| System architecture | [system-architecture.svg](system-architecture.svg) | [system-architecture.png](system-architecture.png) | [system-architecture.mmd](system-architecture.mmd) |
| End-to-end execution flow | [execution-flow.svg](execution-flow.svg) | [execution-flow.png](execution-flow.png) | [execution-flow.mmd](execution-flow.mmd) |

## 01 — System architecture

The runtime is one Uvicorn worker serving the static browser UI and FastAPI ASGI shell. The versioned API adapter applies a streaming 64 KiB body cap, then dispatches the existing synchronous `Handler.route` through Starlette's threadpool. The handler owns route validation, role checks, sessions, incident operations, and remediation endpoints.

The investigation is an in-request LangGraph `StateGraph`. Its nodes resolve an incident's service dependency scope, read service context, then gather logs, metrics, traces, deployment events, and configuration events in sequence. The graph imports `backend.investigation_tools` directly. The separate stdio MCP server wraps the same read-only catalog for a local MCP host; the graph does not call the MCP server.

The tool catalog reads the service registry and incident scenario observations stored in the operational SQLite database. Queries are incident-scoped, limited to 50 records, and bounded to a seven-day window. Missing or unavailable sources remain explicit tool errors.

The deterministic signature engine is authoritative. It abstains when evidence spans fewer than two kinds, any tool error occurred, or a competing signature is too close. If enabled by explicit data consent and valid HTTPS configuration, an OpenAI-compatible endpoint may reorder the fixed candidates and annotate missing evidence. The response cannot add a cause or replace the deterministic root-cause decision; provider failures fall back to the deterministic result.

Operational records (incidents, evidence, events, approvals, actions, verification, evaluations, and audit records) live in `data/opspilot.db`. LangGraph checkpoints use `data/workflow-checkpoints.sqlite` by default; `OPSPILOT_CHECKPOINT_DATABASE_URL` switches only the checkpoint store to PostgreSQL. The incident store remains SQLite.

Remediation is a separate operator-requested API call. A proposal requires a supported diagnosis matching an active seeded replay and an allowlisted action. The exact typed parameters are hashed and immutable; a different approver must approve them within 30 minutes. A different operator executes the action once against simulator state. Server-owned health, symptom, and action-scope checks control resolution.

### Communication and engineering choices

- The API process serves the same-origin browser UI as static HTML, CSS, and JavaScript.
- FastAPI supplies the ASGI lifecycle and middleware, while the adapter preserves the existing synchronous handler API. Investigation executes in the request threadpool.
- LangGraph stores per-run state in a separate checkpointer, so checkpoint storage can be selected independently of incident records.
- Operational records use SQLite with WAL, foreign keys, transactions, and a busy timeout. A hosted database needs its own migration and rollout plan.
- The optional MCP gateway is stdio-only and read-only. It is a second entry point to the shared catalog, not an internal graph transport.
- Prometheus request counters and duration histograms are local. OTLP trace and metric export is enabled only when configured. The backup utility uses SQLite's online backup API, verifies the copy, and records SHA-256 hashes.

### Implemented security and reliability

- Operator and approver use separate shared local credentials and fixed roles. Session tokens are stored hashed; browser sessions use HTTP-only, SameSite cookies, eight-hour expiry, CSRF tokens, and same-origin checks for mutations.
- Mutating browser/API requests require a valid session and CSRF token. Request bodies are capped at 64 KiB and API objects reject unknown fields. Login throttling is in-process.
- The optional alert webhook requires a bearer token, validates its schema, deduplicates correlation IDs, and rejects the same ID with a different payload.
- Read tools enforce incident dependency scope, result limits, and time windows. Tool failures are persisted and prevent a supported diagnosis.
- Investigation idempotency keys reuse completed results and let a failed run attempt checkpoint recovery with the original key. Recovery behavior is backend-dependent and needs validation for each deployment.
- Proposal parameters are immutable and approval is bound to their hash. Execution is once-only and verification is server-owned; a failed check does not resolve the incident.

### Current deployment profile

- Evidence comes from incident and scenario records in SQLite. Reads are bounded by dependency scope, record count, and time window.
- The action executor applies allowlisted changes to simulator state and records server-side verification.
- The runtime uses one Uvicorn worker, separate shared operator and approver accounts, and SQLite for operational records. Checkpoints can use a separate PostgreSQL store.
- Optional model review sends bounded, heuristically redacted evidence to the configured HTTPS provider only after explicit consent.
- The backup utility creates an online SQLite copy, checks integrity, and records a SHA-256 manifest. Hosted deployment still needs managed identity, tenant isolation, coordinated operational storage, shared throttling, and a tested recovery and scale plan.

## 02 — End-to-end execution flow

The representative flow starts when an authenticated operator invokes `POST /api/v1/incidents/{id}/investigate` for an existing incident. Starting a replay and receiving a webhook are separate operations: a webhook creates and records an incident, but does not automatically start the investigation.

The ASGI adapter enforces the body limit and passes the request to the synchronous handler in a threadpool. The handler checks session, role, CSRF/origin, JSON fields, incident state, and the idempotency key. A completed run with the same key returns its stored result. Otherwise, the handler persists an investigation ID and calls the graph with that ID as the checkpoint thread ID.

The graph reads context and evidence in order, deduplicates observations, retains tool errors, and evaluates the deterministic cause signatures. A cause is supported only with at least two evidence kinds, no tool errors, and a lead of at least two evidence kinds over a competing signature. Otherwise, the result is inconclusive and cannot produce a proposal.

The final diagnosis, evidence, tool outcomes, timeline events, and audit entries are committed before the API returns JSON to the console. Optional model review runs only after deterministic candidates exist. A timeout or invalid model response does not block the request or change the deterministic cause.

After a supported result, the operator must explicitly request a proposal. The server checks the active scenario and cause match, then creates a typed, hashed, expiring approval request. Rejection returns the incident to investigation. Expiry blocks execution and requires a fresh investigation and proposal. Once approved, a different operator executes once. The server records health, original-symptom, and scope checks; only a passing result marks the incident resolved.

## Interview walkthrough

### 30 seconds

“OpsPilot is a controlled incident-investigation workspace. An operator starts an investigation, and a checkpointed LangGraph workflow reads incident-scoped evidence through bounded, read-only tools. Deterministic signatures select a cause only when enough independent evidence agrees; an optional consent-gated model can rank those fixed candidates. Any remediation is a separate typed proposal, approved by a second role, executed once by another operator, and resolved only after server-side simulator checks pass.”

### 2 minutes

“The browser is static HTML, CSS, and JavaScript served by a single-process FastAPI/Uvicorn app. The API adapter caps request bodies and hands the existing synchronous route handler to Starlette's threadpool. The handler applies role, session, CSRF, input, and lifecycle checks, then writes incident and audit records to SQLite.

For investigation, the operator supplies an idempotency key. OpsPilot persists a run ID and uses it as the LangGraph checkpoint thread ID. The graph resolves the incident's allowed dependency scope, reads service context, then gathers logs, metrics, traces, deployment events, and configuration events from the shared bounded catalog. The graph calls that Python catalog directly; a separate stdio MCP server exposes the same read-only functions to local MCP clients.

The deterministic diagnosis engine requires cross-source support and abstains on source errors or close competing signatures. If explicit consent and HTTPS provider settings are present, the optional model sees bounded, heuristically redacted observations and a fixed candidate list. It may reorder candidates but cannot invent the cause or authorize action.

Completed evidence, tool outcomes, result, and audit trail are persisted before returning to the console. A supported result still does not execute anything: an operator must request an allowlisted proposal, another person must approve the exact hashed parameters before expiry, and a different operator must execute it. The executor changes only simulator state and the server records the verification checks. Only passing checks resolve the incident.”

### Interview questions

1. **Why does the graph call Python tools directly instead of going through MCP?** The workflow imports the shared `investigation_tools` module directly. MCP is a separate stdio adapter for external local clients; it is not an internal transport dependency.
2. **What makes a diagnosis supported?** At least two distinct evidence kinds must match a deterministic signature, there must be no tool errors, and the top signature must lead a competing signature by at least two evidence kinds. Otherwise the engine abstains.
3. **What authority does the LLM have?** None over cause selection or actions. With explicit consent and valid HTTPS configuration it can reorder up to four deterministic candidates and annotate missing evidence. Invalid or unavailable output falls back.
4. **How do you prevent unsafe or duplicate remediation?** The server requires an active matching simulator case and a catalog action, hashes immutable parameters, requires a distinct unexpired approver, requires a different operator to execute, and allows one execution per proposal.
5. **What would need to change before hosted production use?** Add managed per-user identity and tenant isolation, coordinated operational storage and migrations, shared throttling, external observability adapters, a tested recovery and scale plan, and deployment-level authorization. Keep remediation bound to its simulator until a separately designed production control plane is reviewed.

## Validation summary

- **Inspected:** `app.py`, `backend/asgi.py`, `backend/workflow.py`, `backend/investigation_tools.py`, `backend/llm.py`, `backend/mcp_server.py`, `backend/telemetry.py`, `scripts/backup.py`, `README.md`, `docs/architecture.md`, `docs/api.md`, `docs/security.md`, and `docs/runbook.md`.
- **Verified:** the ASGI-to-handler threadpool adapter; direct graph-to-tool-module calls; distinct MCP stdio wrapper; SQLite operational store and separate checkpoint choice; deterministic diagnosis gates; consent/HTTPS candidate-only ranking; alert dedupe; role separation and immutable proposal workflow; simulator-only execution and server-side verification.
- **Scope confirmed:** bounded scenario reads, deterministic diagnosis, optional candidate ranking, simulator action execution, shared local roles, SQLite operational records, and a single-process API runtime.
- **Rendering:** SVG masters exported to PNG at 2400 px wide with Microsoft Edge headless rendering. Visual inspection performed for clipping, labels, connector direction, and page balance. Mermaid sources are provided as editable topology/flow references; no Mermaid CLI is installed in the workspace.
- **Locations:** all deliverables are in `docs/portfolio-diagrams/`.
