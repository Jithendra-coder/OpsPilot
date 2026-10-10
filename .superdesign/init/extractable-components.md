# Extractable component catalog

The console uses inline HTML templates in `web/app.js`; there are no React/Vue components to extract. These repeated layout patterns should remain consistent in design variants:

## Sidebar
- Source: `web/index.html` (`.sidebar`)
- Category: layout
- Description: Brand, workspace identity, primary section navigation, simulator boundary, signed-in role, and sign-out control.
- Extractable props: active navigation item, role label, incident count, pending approval count.
- Hardcoded: Brand name and icon shapes; local-only safety copy.

## Topbar
- Source: `web/index.html` (`.topbar`)
- Category: layout
- Description: Current section breadcrumb, environment indicator, and new-incident action.
- Extractable props: current section, role-gated new-incident visibility.
- Hardcoded: Workspace label and local environment text.

## PageHeading
- Source: `web/app.js` (`heading()`)
- Category: basic
- Description: Page heading, concise task description, and right-aligned page actions.
- Extractable props: title, description, actions.

## MetricCard
- Source: `web/app.js` (`stat()`)
- Category: basic
- Description: Overview metric with a value, icon, and short contextual note.
- Extractable props: label, value, footnote, visual state, icon name.

## IncidentRow
- Source: `web/app.js` (`incidentRows()`)
- Category: basic
- Description: Incident title and ID paired with service, owner, severity, status, and recency.
- Extractable props: incident fields and compact mode.
- Hardcoded: Field labels and status/severity treatment.
