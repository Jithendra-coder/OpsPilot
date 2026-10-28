# OpsPilot: project outcome and resume brief

## Project description

OpsPilot is an incident investigation and controlled-response platform for SRE and backend teams. It connects alert intake to service-scoped logs, metrics, and traces; builds a timestamped evidence record; and explains which supported failure signature the evidence matches. If a response is eligible, one role proposes it, a different role approves the exact action, and the server verifies the result. Actions are restricted to an isolated simulator.

## Outcome the project targets

Give an on-call engineer one reviewable path from a service alert to a defensible next step:

1. Receive and deduplicate an alert for a registered service.
2. Retrieve bounded observations from the incident's service dependency scope and time window.
3. Preserve evidence provenance, timestamps, tool results, and uncertainty with the incident.
4. Compare the observations with supported failure signatures; leave the result inconclusive when evidence is weak, conflicting, or unavailable.
5. Present an approval-gated response only for an eligible simulator case, then verify and audit the simulated outcome.

The product goal is faster, more consistent incident review with a human-controlled response boundary. No MTTR reduction, field accuracy, or production availability result is claimed because those have not been measured against an operational deployment.

## What is implemented

- Alert intake through normalized webhooks and Alertmanager, with authenticated delivery, correlation, deduplication, and audit events.
- Bounded, read-only Prometheus, Loki, and Tempo adapters, plus normalized observation intake. Queries are constrained by service scope, incident window, result counts, response size, and time limits.
- A LangGraph investigation flow that gathers logs, metrics, traces, and change observations; runs deterministic evidence-linked diagnosis; and optionally uses a model only to reorder existing candidates.
- SQLite for a local install or PostgreSQL for operational persistence; LangGraph checkpoints can share PostgreSQL. Named operator and approver accounts have distinct permissions.
- A reviewable action lifecycle: typed allowlist, immutable action parameters, separate approval, idempotent execution, simulator-only effects, and server-side verification.
- Browser console, interactive API-backed CLI, versioned JSON API, and ten read-only incident-scoped MCP tools.
- A Compose demo with an instrumented checkout service, Prometheus, Alertmanager, OpenTelemetry Collector, Loki, Tempo, PostgreSQL, and OpsPilot. It demonstrates real local telemetry ingestion and verifies the external-action boundary.
- Seeded replay cases for a deterministic approval walkthrough, a CLI-only package, container build, operational documentation, and automated checks.

## Demonstrable result

The live demo can generate a checkout database-pool fault, produce metrics, logs, and traces, fire an Alertmanager notification, create an OpsPilot incident, collect observations from all three providers, and produce the supported database-pool diagnosis. It also checks that the provider-backed incident cannot invoke the simulator action route. The separate seeded walkthrough demonstrates proposal, approval, execution, and server-recorded verification.

The included fixture catalog has 36 replay cases (28 supported and 8 expected-inconclusive) and a 17-case evidence-composition set (13 supported and 4 expected abstentions after signal mapping). These check implementation consistency; they are not independent accuracy benchmarks.

## Resume-ready entry

**OpsPilot — Incident Investigation and Controlled Response Platform** | Python, FastAPI, LangGraph, PostgreSQL, SQLite, Prometheus, Loki, Tempo, OpenTelemetry, Docker Compose

- Built an incident workflow that ingests normalized and Alertmanager events, retrieves service- and time-scoped telemetry from Prometheus, Loki, and Tempo, and links evidence provenance to deterministic root-cause findings.
- Orchestrated investigations with LangGraph and durable SQLite/PostgreSQL checkpoints; kept missing, conflicting, or unavailable evidence explicit so unsupported diagnoses remain inconclusive.
- Implemented role-separated action review with immutable proposals, idempotent simulator execution, audit history, and server-side verification; blocked remediation for externally sourced incidents.
- Packaged an isolated Compose demo that generates a controlled service fault and carries it through alert delivery, telemetry collection, diagnosis, and safety-boundary verification.
- Delivered browser and interactive CLI interfaces, versioned APIs, and read-only MCP tools for incident-scoped investigation.

## STAR interview answer

**Situation:** Incident responders often have to correlate alerts with logs, metrics, traces, and recent changes across separate tools. Automated remediation also needs a clear review boundary so an uncertain diagnosis cannot directly change a service.

**Task:** Build a demonstrable incident workflow that consolidates scoped evidence, explains its diagnosis, and records a controlled response without taking action on real infrastructure.

**Action:** Implemented authenticated alert intake and bounded Prometheus, Loki, and Tempo readers; orchestrated evidence collection and deterministic signature matching with LangGraph; added persistent incident/checkpoint storage, named operator and approver roles, immutable proposals, simulator-only execution, and verification. Built a Compose lab that emits real local telemetry and exercises the alert-to-diagnosis flow.

**Result:** OpsPilot demonstrates an end-to-end, auditable incident path from an Alertmanager event through three telemetry sources to an evidence-linked diagnosis, while rejecting external remediation. Its seeded workflow separately demonstrates human approval and verified simulator execution. This is a verified portfolio-lab result, not a measured production MTTR or diagnosis-accuracy claim.

## Scope to describe accurately

OpsPilot is a portfolio lab and integration example, not a hosted-production incident platform. The Compose demo instruments its own checkout service; connecting another service requires configuring and validating provider mappings or submitting normalized observations. Remediation remains simulator-only. SSO, MFA, tenant isolation, high availability, and independently validated field accuracy are outside the current implementation.
