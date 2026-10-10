# Routes and views

There is no client-side routing library. FastAPI serves the product introduction at `/`, the authenticated console at `/console` (and the legacy `/index.html` route), and the bundled demo media as static assets. Within the console, `web/app.js` validates `location.hash`, chooses a view in `render()`, and updates the same `#page-content` region. API behavior is dispatched through `/api/v1/*`.

| View | URL fragment | Renderer | Purpose |
| --- | --- | --- | --- |
| Introduction | `/` | `web/intro.html` | Product purpose, evidence-led workflow, safety boundary, and captioned demo. |
| Console sign-in and Overview | `/console#overview` | `renderOverview()` | Authenticated incidents, service health, activity, and replay entry point. |
| Incidents | `#incidents` | `renderIncidents()` | Searchable and filterable incident list. |
| Service map | `#services` | `renderServices()` | Dependency topology and registered service health. |
| Investigation | `#investigation` | `renderInvestigation()` | Evidence, hypotheses, actions, and incident timeline. |
| Approval center | `#approvals` | `renderApprovals()` | Independent approval of exact allowlisted actions. |
| Replay lab | `#lab` | `renderLab()` | Seeded scenario replay and diagnosis benchmark. |

The shell also contains the authentication screen and a shared modal used by incident creation, approval decisions, execution confirmation, escalation, and notes.
