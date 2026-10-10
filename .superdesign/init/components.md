# Reusable UI components

Framework: plain HTML and JavaScript. There is no React/Vue component library, no component directory, and no shared design-system package.

Reusable UI templates live in `web/app.js` and are inserted into the application shell in `web/index.html`.

- `icon(name, className)` — inline SVG icon primitive from the local `icons` catalog.
- `heading(title, description, actions)` — page title, supporting description, and optional actions.
- `stat(label, value, foot, kind, iconName)` — overview metric card.
- `incidentRows(items, compact)` — compact incident list with status and age.
- `serviceLines(services)` — service-health rows.
- `activityList(events)` — recent activity timeline rows.

All page and shell source is in `web/index.html`, `web/app.js`, and `web/app.css`; there are no component files to include individually.
