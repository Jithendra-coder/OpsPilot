# Page dependency trees

All views render into the shared shell; they are functions in one browser script rather than separate files.

## `/` — Product introduction
- `web/intro.html` — product narrative, seeded-case preview, workflow, safety model, and demo player.
- `web/intro.css` — responsive introduction-page styles and reduced-motion/accessibility behavior.
- `web/demo.webm` and `web/demo-captions.vtt` — local narrated product walkthrough and caption track.
- `web/favicon.svg` — local OpsPilot brand mark.

## `/console` — Sign-in and Overview
- `web/index.html` — sign-in screen, app shell, sidebar, top bar, page mount, modal, and notifications.
- `web/app.js` — `loadSession()`, `refresh()`, `render()`, `renderOverview()`, `heading()`, `stat()`, `incidentRows()`, `serviceLines()`, `activityList()`, `icon()`.
- `web/app.css` — global tokens, shell, overview cards, responsive breakpoints, focus and reduced-motion behavior.
- `web/favicon.svg` — local OpsPilot brand mark.
- Backend APIs: `/api/v1/overview`, `/api/v1/incidents`, `/api/v1/scenarios`, `/api/v1/approvals`.

## `#incidents` — Incident list
- Shared shell: `web/index.html`.
- Renderer and events: `web/app.js` — `renderIncidents()`, filters, search, incident open action.
- Styles: `web/app.css` — `.incident-table`, `.table-toolbar`, `.incident-row`.
- Backend APIs: `/api/v1/incidents`, `/api/v1/incidents/{id}/report`.

## `#services` — Service map
- Shared shell: `web/index.html`.
- Renderer: `web/app.js` — `renderServices()`, `serviceName()`, `icon()`.
- Styles: `web/app.css` — `.service-map`, `.map-stage`, `.service-node`, `.service-line`.
- Backend API: `/api/v1/overview`.

## `#investigation` — Investigation workspace
- Shared shell: `web/index.html`.
- Renderer and actions: `web/app.js` — `renderInvestigation()`, `openIncident()`, `startInvestigation()`, `proposeRemediation()`, `exportReport()`.
- Styles: `web/app.css` — `.workspace-layout`, `.evidence-item`, `.hypothesis-card`, `.timeline-mini`, `.recommendation-card`.
- Backend APIs: incident report, investigation, remediation proposal, notes, simulation reset, report export.

## `#approvals` — Approval center
- Shared shell: `web/index.html`.
- Renderer and actions: `web/app.js` — `renderApprovals()`, `approvalDecisionModal()`, `executeApproved()`.
- Styles: `web/app.css` — `.approval-card`, `.approval-action`, `.approval-guidance`.
- Backend APIs: `/api/v1/approvals`, approval decision, action execute, verification.

## `#lab` — Replay lab
- Shared shell: `web/index.html`.
- Renderer and actions: `web/app.js` — `renderLab()`, `replay()`, `runEvaluation()`, report export.
- Styles: `web/app.css` — `.lab-grid`, `.scenario-card`, `.evaluation-card`.
- Backend APIs: scenarios, simulation start/reset, evaluation.
