# OpsPilot project readiness audit

**Assessment branch:** `review/opspilot-audit`

**Scope:** local portfolio profile, source and API review, automated tests, a temporary-directory application run, and browser accessibility-tree inspection of `/` and `/console`.
**External verification limits:** no authorized Prometheus endpoint, live model, PostgreSQL checkpoint service, Git remote, Docker CLI/Buildx, or production deployment was available. Podman 6.0.2 was available and used for the local container build and health check described below.

The previous `86/100` report used a different weighting. This report uses the 30/25/15/10/10/10 rubric from the readiness brief; the scores are not directly comparable.

## 1. Project overview

OpsPilot is an incident investigation and controlled-remediation portfolio application for SRE and on-call operators. It accepts an incident and scoped evidence, selects a supported cause or abstains, proposes an allowlisted action, requires a separate approval, executes only against the seeded simulator, and records server-side verification.

The core local workflow is implemented. Evidence can come from replay cases, operator or authenticated webhook submissions, and an optional bounded Prometheus reader. Diagnosis is deterministic over supported signal IDs. The optional LLM can reorder a fixed candidate list; it is not the root-cause authority. Incident and approval records use SQLite; LangGraph checkpoints use SQLite by default. The UI is static HTML, CSS, and JavaScript served with the API.

## 2. Initial readiness score

This is the score for the repository state before linking the existing CI matrix to the image/release jobs and before refreshing this report.

| Category | Score | Evidence and deduction |
| --- | ---: | --- |
| Core purpose and functionality | 26/30 | The seeded incident-to-verified-recovery workflow and normalized evidence intake are implemented. Deducted because most logs, traces, and change records require caller-supplied signal IDs; no real source mapping or live provider was validated. |
| AI/ML accuracy and evaluation | 17/25 | 36 catalog cases check 28 supported outcomes and 8 expected abstentions; a separate 17-case set checks signal-level cause selection and abstention. Both are authored around the engine's signal vocabulary; raw telemetry classification, field accuracy, and LLM quality are unmeasured. |
| Architecture and code quality | 13/15 | A modular monolith fits the local workflow, and the separate checkpoint store, tool catalog, and simulator executor have clear roles. API behavior remains concentrated in a synchronous handler; hosted storage and identity are absent. |
| Security and reliability | 8/10 | Session/CSRF checks, scoped inputs, bounded requests, approval separation, idempotency, verification, and restore checks are covered. Shared local credentials, process-local throttling, heuristic redaction, and the lack of a penetration test limit the score. |
| Testing and reproducibility | 8/10 | 39 tests pass locally and cover API integration, safety boundaries, recovery, and persistence. CI already had a three-version Python matrix, but container build and release jobs were not linked to it. Dependencies are ranged rather than fully locked. |
| Portfolio and demonstration quality | 8/10 | Setup, API/security/runbook docs, editable diagrams, an introduction page, and a captioned product walkthrough are present. A complete keyboard/screen-reader and responsive visual review was not recorded; the video is motion graphics rather than a live browser recording. |
| **Initial total** | **80/100** | Reviewer-scored against the required rubric; this is not a measured product metric. |

## 3. Core goal verification

**Does OpsPilot accomplish its goal?** It demonstrates a complete, safety-gated workflow for the local replay lab and accepts normalized incident evidence. It does not yet establish reliable autonomous investigation of arbitrary live incidents.

| Stage | Expected | Verified result | Status |
| --- | --- | --- | --- |
| Intake | Validate an incident and bounded evidence | Manual and authenticated webhook intake, deduplication, dependency scope, timestamps, and supported signal-kind checks are covered by API tests. | Pass for local contract |
| Evidence reads | Gather incident-scoped logs, metrics, traces, and changes | Seeded and submitted evidence paths are tested. Prometheus HTTP behavior is tested with mocked responses; the live query mapping is not. | Partial for external sources |
| Diagnosis | Compare supported causes and abstain on weak/conflicting evidence | 36 catalog cases and 17 signal-composition cases pass; classification starts after a signal ID has been assigned. | Pass at signal-decision layer; unverified at raw-source layer |
| Proposal and approval | Prevent investigation from authorizing its own change | Tests verify typed allowlisting, immutable parameters, separate approver/operator roles, expiry, and rejection paths. | Pass for simulator |
| Execution and verification | Execute once and close only after server-owned checks | End-to-end API tests verify idempotent simulator execution and server-recorded checks. | Pass for simulator |
| Report | Preserve evidence and action history | API integration tests cover evidence provenance, events, and the incident report. | Pass for local data |

The core purpose gate is therefore **partial**: the local controlled workflow is complete, while source authentication/mapping and live-provider behavior remain unverified. No evidence supports a field-accuracy claim.

## 4. Architecture assessment

The browser and versioned API run in one FastAPI/Uvicorn process. A compatibility adapter applies request-size limits and calls the synchronous handler through Starlette's thread pool. SQLite stores incidents, evidence, audit, approvals, actions, and verification. LangGraph persists investigation progress in a separate SQLite checkpoint file by default. A shared bounded read-only tool catalog is also exposed through a local stdio MCP server. The typed executor changes only seeded simulator state.

The modular monolith is proportionate to this portfolio workflow. Keep it as the recommended architecture; add provider adapters behind the existing bounded read-only tool interface, and introduce managed identity or shared storage only for a defined hosted deployment. No broker, vector database, production executor, or additional agent is justified by verified requirements. Earlier cleanup removed a graph context lookup whose results were unused and a duplicate change-record read. The current diagram sources are [system architecture](portfolio-diagrams/system-architecture.mmd) and [execution flow](portfolio-diagrams/execution-flow.mmd); the image exports are maintained alongside them.

Key design limits are single-process shared local credentials, SQLite operational data, separate incident/checkpoint stores, operator-managed PromQL mappings, and no built-in provider reader for logs, traces, or deployment events.

## 5. AI/ML accuracy report

OpsPilot has no trained classifier or retrieval index. Its authoritative diagnosis matches supported `signal_id` values to a fixed cause catalog, compares support across evidence kinds, and abstains when evidence is incomplete, conflicting, or a tool failed. The support score is a heuristic, not a calibrated probability. The optional HTTPS model ranks existing candidates only.

| Evaluation | Results | What it supports | What it does not support |
| --- | --- | --- | --- |
| Seed catalog | 28/28 labeled cases match the expected cause; 8/8 unlabeled cases remain inconclusive. | Rule/catalog consistency over the bundled replay cases. | Independent accuracy: expected labels and signals are part of the same authored catalog. |
| Signal-composition set | 13/13 supported decisions and 4/4 expected abstentions; no false supported case in 17 cases. | Cause selection and abstention after signals are already mapped. | Raw text/log classification, source mapping quality, field accuracy, or generalization. |
| Optional model | No live provider evaluation was run. | Its code path is bounded to reordering the fixed candidates and falls back on errors. | Quality, latency, cost, prompt-injection resistance against a real provider, or measurable benefit. |

No before/after model improvement is claimed. The main accuracy blocker is independently labeled raw operational evidence and verified source mapping, not another model or larger synthetic fixture set.

## 6. Cleanup and simplification

| Component | Decision | Reason and verification |
| --- | --- | --- |
| FastAPI plus synchronous handler | Keep | One local deployable process fits the present scale; request/body/auth tests exercise the adapter. Splitting routers has no demonstrated benefit yet. |
| SQLite incident store | Keep for local profile; defer hosted use | Migrations, integrity checks, backup, and restore are covered. It does not provide multi-replica coordination or hosted identity. |
| LangGraph checkpoint | Keep | Recovery and cold concurrent setup have regression tests. PostgreSQL checkpoint operation remains unverified. |
| Deterministic signature engine | Keep and evaluate further | It is bounded and can abstain; its quality is measured only after mapping to supported signal IDs. |
| Optional LLM ranking | Defer expansion | Disabled unless consent and HTTPS settings are present; no comparative quality or cost evidence justifies making it central. |
| Read-only MCP catalog | Keep | Reuses the same incident-scoped tool functions for a local MCP client; it is not exposed as a network service. |
| Replay lab and 36 cases | Keep | Useful for repeatable workflow and safety demonstrations; label results as catalog consistency. |
| Shared operator/approver accounts | Keep only for local lab | Distinct roles demonstrate separation of duties, but they are not individual identities or tenant authorization. |
| Prometheus reader | Keep, live validation pending | Time, response, query-count, redirect, and signal bounds are implemented and mock-tested. Query correctness depends on operator configuration. |
| CI, container, and release jobs | Keep, consolidated and gated | One Python 3.11–3.14 matrix now precedes image build and publication, avoiding duplicate test workflows. Actions and Python dependencies are pinned or bounded and monitored weekly by Dependabot; `pip-audit` gates the container jobs. The Docker-format image built and passed a local Podman startup/health check; GitHub execution and image publication remain unverified. |
| Duplicate graph context and change reads | Remove | Their outputs were unused or repeated; the investigation graph now calls the necessary evidence readers once. |
| Hosted identity, log/trace vendor adapters, production executor | Defer | These require source-specific credentials, deployment requirements, threat modeling, and independent verification not available in this workspace. |

## 7. End-to-end test results

The project virtual environment ran `python -m unittest discover -s tests`: **39 passed, 0 failed, 0 skipped**. The same 39 tests passed inside the Docker-format Python 3.12 image and in isolated Python 3.11, 3.13, and 3.14 environments. `pip check` passed in each newly prepared environment. The suite includes diagnosis/abstention, API-to-report evidence, mocked Prometheus API intake, authentication and throttling, MCP boundaries, action approval and verification, migration preservation, backup/restore integrity, and checkpoint recovery. The original local virtual environment uses Python 3.10, which reached end of life on 2026-10-01. CI now targets maintained Python 3.11–3.14; GitHub-hosted execution and release publication remain unverified.

Additional checks recorded in the prior local engineering pass: 20 repeated eight-way cold-checkpoint runs passed; 80 seeded investigations completed in 11.513 seconds at concurrency 8 with no failed responses; an earlier 200-request local health smoke measured about 405 requests/second, 18.57 ms median, and 24.09 ms p95. A repeat in this pass measured 214 requests/second, 28.51 ms median, and 42.57 ms p95 at the same request count and concurrency. These are variable loopback readiness-only samples using temporary local state, not a target deployment or capacity claim; the graph cleanup has no separate before/after latency measurement. The Docker-format image also built with Podman, ran as UID 10001, returned a healthy API response, and passed its configured image health check. This pass also opened `/` and `/console` against a temporary data directory and inspected their accessibility trees: the introduction exposes skip navigation, section links, and Get started; the console exposes a labeled password field and sign-in button.

Reproduce locally with:

~~~powershell
python -m unittest discover -s tests
python -m compileall -q app.py backend scripts
node --check web\app.js
python -m pip check
~~~

The first test command using the system Python failed to import project dependencies. The repository virtual environment contains the dependencies and is the valid local test environment. The CI matrix now gates container build and release in the same workflow, but no hosted run was possible because this checkout has no Git remote or matching OpsPilot repository. The local Docker-format container build and health smoke passed using Podman; Docker CLI/Buildx and release publication were not run. Browser keyboard/screen-reader checks, live Prometheus/model calls, PostgreSQL recovery, deployment rollback, and cross-host restore were not run.

## 8. Security and reliability

**Confirmed critical defects:** none in the reviewed local simulator workflow. The previous pass fixed a medium local-service weakness in login throttling: reservations are atomic, stale entries are pruned, and the in-memory address table is bounded. Tests cover concurrent attempts, lockout, and capacity.

On 2026-10-10, `pip-audit -r requirements.txt` found no known vulnerabilities for the compatible package resolutions it checked. A local scan of 97 current text files and the repository's single commit found no matches for the selected private-key, provider-token, cloud-key, embedded-URL-credential, or plaintext-secret patterns. No dedicated secret-scanning utility was installed, so this is a targeted scan rather than an exhaustive certification. The local SQLite database and virtual environment are ignored by Git.

Implemented safeguards include bounded request and observation sizes; session cookies, CSRF and same-origin checks; role checks; dependency scope; authenticated webhook intake with deduplication; read-only evidence tools; no redirects and bounded Prometheus responses; consent-gated HTTPS model calls; typed simulator-only actions; immutable approval parameters; independent approval; execution idempotency; server-owned verification; and checksum/integrity-checked restore to a new directory.

Remaining risks: local shared credentials are not managed user identities; the limiter is per process; SQLite does not provide tenant isolation or multi-replica writes; operator-authored source mappings are not independently validated; model redaction is heuristic; and no penetration test, production TLS proxy test, external failure drill, or hosted restore rehearsal was performed. Do not expose this profile as a shared production service.

## 9. Improvements implemented

| Problem | Change | Verification and benefit | Remaining limit |
| --- | --- | --- | --- |
| Container PR builds and tag releases were independent of the test matrix. | Consolidated image build and publication as dependent jobs in the existing Python 3.11–3.14 CI workflow, pinned all actions to release commits, added weekly Python and action updates, and gated builds on `pip check` and `pip-audit`. | Local tests/static checks and dependency audit pass; workflow YAML and job dependencies are checked; the Docker-format image builds and its readiness health check passes locally with Podman. The gate prevents downstream jobs when CI verification fails. | A GitHub-hosted run and registry publication were not possible without a remote. |
| The readiness report used a different scoring rubric and did not answer every required section. | Replaced it with the 12-section report and the prompt's exact weighted categories, gates, limitations, and remaining-work table. | Scores now distinguish catalog consistency from raw-source accuracy and mark live integrations as unverified. | Scores remain evidence-based reviewer judgments, not measured product performance. |
| Duplicate investigation reads added work without contributing to diagnosis. | Removed the unused context read and duplicate change query from the graph. | Workflow integration tests pass and confirm expected graph stages. | Latency reduction was not separately measured. |
| Diagnosis confidence could be mistaken for probability. | UI and documentation identify the value as heuristic support; evaluation copy names catalog consistency. | UI/API wording is covered by tests. | Statistical calibration needs independent labels. |
| Local recovery and concurrency needed stronger checks. | Added cold-start checkpoint setup serialization, bounded busy wait, verified new-directory restore, and reproducible evaluation/load scripts in the prior pass. | Regression tests, repeated cold runs, and temporary-state load checks passed as listed above. | Multi-process and deployed recovery are unverified. |

## 10. Final scorecard

| Category | Maximum | Initial | Final verified | Final deduction |
| --- | ---: | ---: | ---: | --- |
| Core purpose and functionality | 30 | 26 | 26 | Live source mappings and real provider behavior are not verified; most text requires pre-mapped signals. |
| AI/ML accuracy and evaluation | 25 | 17 | 17 | Authored signal-level cases do not establish raw telemetry or field accuracy; no LLM comparison. |
| Architecture and code quality | 15 | 13 | 13 | Local handler concentration and hosted storage/identity boundaries remain. |
| Security and reliability | 10 | 8 | 8 | No managed identities, multi-tenant controls, shared limiter, or penetration test. |
| Testing and reproducibility | 10 | 8 | 9 | 39 local tests pass and build/release are now gated by the CI matrix; hosted execution and exact dependency lock are still absent. |
| Portfolio and demonstration quality | 10 | 8 | 8 | Strong setup/docs/diagrams and introduction; visual/keyboard audit and live-session video are not verified. |
| **Total** | **100** | **80** | **81** | **The mandatory 95+ gates are not met.** |

## 11. Remaining work to reach a legitimate 95+

| Priority | Impact | Recommended fix | Verification method | Completion criteria |
| --- | --- | --- | --- | --- |
| P1 | Establish whether evidence mappings and diagnosis work on actual operations data. | Connect an authorized read-only Prometheus source; add source-authenticated log, trace, and change adapters or collectors; review each mapping. | Replay incidents against the approved endpoint and compare evidence provenance, timestamps, service scope, and query results with source records. | Every reported signal traces to an authorized source record; provider errors abstain; no unsupported signal can select a cause. |
| P1 | Measure raw-input diagnosis and avoid testing only the engine's own vocabulary. | Build an independently labeled, held-out incident set with raw logs/metrics/traces, source mapping labels, and explicit no-cause/ambiguous cases. Establish a baseline before changing logic. | Report source-mapping precision/recall, cause-selection precision/recall, false-supported rate, abstention behavior, and comparable latency/cost. | Independent evaluation demonstrates target quality without tuning on the held-out set; claims match measured scope. |
| P1 | Demonstrate safe operation in the intended deployment. | Run the GitHub-hosted CI pipeline, deploy the locally validated image behind the intended TLS proxy, rehearse backup restore and rollback, and measure on the intended host. | Record CI run IDs, image digest, TLS/proxy checks, restore result, rollback result, and bounded load/failure tests. | Clean deployment, recoverable data/checkpoints, tested rollback, and measured service limits. |
| P2 | Protect shared or hosted users and incident data. | Add managed per-user identity, authorization/tenant isolation, shared rate limiting, reviewed operational database migrations, and source-specific redaction. | Security review plus authorization/tenant-isolation, rotation/revocation, load, and penetration tests. | No cross-tenant reads or writes; revocation and limits work across replicas; findings remediated. |
| P2 | Verify the full user-facing experience. | Run responsive browser, keyboard, screen-reader, and video playback checks at supported breakpoints. | Record actual interaction results, accessibility findings, and repaired regressions. | All essential workflows are operable without a mouse; labels, focus, errors, and video captions work. |
| P3 | Claim calibrated support or model benefit. | Only after enough independent labels exist, calibrate the deterministic support score and compare the optional model against a no-model baseline. | Held-out calibration and quality/latency/cost comparison. | Improvement is repeatable and material; otherwise retain the simpler deterministic system. |

## 12. Final readiness verdict

**PORTFOLIO READY — 81/100 for the documented local simulator profile. Not HIGH-CONFIDENCE PORTFOLIO READY (95+), and not production-oriented.** The seeded end-to-end workflow, approval boundary, recovery behavior, locally built container, local setup, and component-level evaluations are defensible. The 95+ gates fail because authentic source mappings and live integrations are unverified and the central diagnosis has not been evaluated on independently labeled raw operational evidence. The configured CI gate was not exercised on GitHub.

Do not present the signal-composition scores as field accuracy or the local smoke results as deployment capacity. The next meaningful step is an authorized real-source evaluation, followed by source-mapping and diagnosis measurements on a separate labeled set.
