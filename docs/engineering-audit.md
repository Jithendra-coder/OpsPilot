# OpsPilot project verification

Checked on 2026-10-28 against the working `main` checkout. This document reports reproducible project behavior; it does not assign an absolute readiness score.

## What the project delivers

OpsPilot is an incident investigation and controlled-response platform for SRE and backend teams. It accepts normalized alerts, gathers incident- and service-scoped observations, records provenance and tool outcomes, and evaluates supported causes deterministically. It leaves weak, conflicting, or unavailable evidence inconclusive. An eligible response is a separate typed proposal, reviewed by an approver role, executed once against the seeded simulator, and closed only after server-owned checks pass.

The product includes a browser introduction and console, interactive CLI, versioned API, ten read-only MCP tools, SQLite or PostgreSQL operational storage, checkpointed LangGraph investigations, backup and restore utilities, and a Compose telemetry demo.

## Verified behavior

- A local Compose demo instruments its own checkout service. Prometheus sends a real alert through Alertmanager; OpenTelemetry sends generated logs and traces to Loki and Tempo. OpsPilot reads all three provider APIs through bounded adapters.
- The freshly rebuilt local Compose demo passed `python -m scripts.demo verify`: the alert created an incident, Prometheus/Loki/Tempo evidence supported the `db_pool` finding, and the external-source incident was rejected at the simulator remediation boundary.
- The seeded guided replay separately covers the typed proposal, approver-role review, one-time simulator execution, and server-side verification.
- The full local unit/integration suite ran 66 tests: 64 passed and the two Postgres-only tests were skipped without a configured database. The PostgreSQL-backed platform and migration run passed all 23 tests.
- Python compilation, `node --check web/app.js`, `pip check`, `pip-audit -r requirements.txt`, the CLI bundle builder, the 17-case signal-composition evaluation, and the Compose configuration check passed. `pip-audit` reported no known vulnerabilities. The signal-composition evaluation supports consistency after signals have been mapped; it is not a raw-telemetry or field-accuracy benchmark.

## Evaluation scope

The seeded catalog contains 36 cases: 28 expected supported outcomes and 8 expected abstentions. The separately authored 17-case composition set contains 13 supported cases and 4 expected abstentions; all matched their authored expectations in the current run. These cases use OpsPilot's supported signal IDs, so they do not establish independent diagnosis accuracy, provider-mapping quality, or model benefit.

## Current boundary

OpsPilot is a complete controlled portfolio product and integration demo. It is not a hosted-production incident platform. The live Compose sources are its own isolated checkout service; connecting another system requires the operator to configure and validate its source mappings. Remediation targets only the seeded simulator. There is no SSO/MFA, tenant isolation, high-availability deployment, shared rate limiting, independently labeled raw incident corpus, or measured MTTR/field accuracy. GitHub Actions is configured to run the automated suite and live demo on push; this document does not claim hosted deployment or capacity verification.

Do not present fixture scores as field accuracy, the local Compose lab as an external customer integration, or local health checks as capacity results. The strongest resume claim is the verified end-to-end workflow with explicit evidence provenance and a human approval boundary.
