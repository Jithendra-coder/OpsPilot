# OpsPilot design system

## Product and audience
OpsPilot is a local incident-intelligence workbench for SREs and backend teams. It must demonstrate one complete, trustworthy story on camera: a controlled incident appears, scoped evidence is gathered, competing causes are evaluated, an exact typed remediation is proposed, another role approves it, and server-side checks report the outcome. It is a real application with real API-backed states; demo polish must not imply live production telemetry or hide the simulator boundary.

## Direction
Keep the requested minimalist approach and OpsPilot's green identity. Upgrade the current small, pale console into a confident editorial operations workspace with strong type hierarchy, legible evidence, one unmistakable primary action per state, and a guided demo path. The first screen should quickly tell a viewer what OpsPilot does and what they can safely inspect. Use actual seeded case data and label it as a controlled simulation. Avoid generic AI graphics, fabricated live metrics, decorative gradients, tiny text, and dashboard-card overload.

## Existing tokens and components
The current source tokens are preserved in `.superdesign/init/theme.md`. The brand uses an inline three-bar mark and wordmark. The existing icon catalog is inline SVG in `web/app.js`. Existing reusable templates include the persistent sidebar, top bar, page heading, metric card, incident row, evidence item, hypothesis card, approval card, and timeline row.

The draft named `Current OpsPilot Overview` is a baseline reproduction: match the supplied HTML, CSS, and the authenticated `renderOverview()` output exactly; do not apply the refinement notes below to that baseline. Branch variations may refine layout, hierarchy, copy, and type scale while preserving the existing light surface, restrained green identity, and current brand mark.

## Visual system to refine
- Canvas: near-white warm gray; raised surfaces: white; use separators and subtle shadow sparingly.
- Primary ink: dark forest/charcoal with readable secondary text. Preserve green as the action and verified-success color.
- Status colors: restrained red for P1/failed, amber for pending/uncertain, blue for evidence/source, green for healthy/verified. Never rely on color alone.
- Typography: system sans with Inter when installed; minimum 12px for supporting text, 14–16px for body text, 28–36px for primary page titles, 18–24px for section titles.
- Spacing: 4/8/12/16/24/32/48px rhythm; comfortable cards; consistent 8–14px radius.
- Desktop: stable 240–264px navigation rail; content max-width about 1360px; align headings, tables, and panels to one grid.
- Responsive: retain labels/navigation at tablet where possible; on mobile use a labeled bottom navigation, stack detail panes, keep buttons at least 40px high, and avoid horizontal overflow.
- Motion: brief transitions only; honor `prefers-reduced-motion`.
- Accessibility: visible keyboard focus, semantic headings and landmarks, 4.5:1 body contrast, descriptive labels, and no status conveyed only by color.

## Demo narrative and interaction
1. Explain the product outcome in one sentence and show a clear `Run guided incident` action.
2. Launch a genuine seeded database-pool scenario through the existing simulation API.
3. Reveal the investigation sequence with evidence provenance, timestamps, confidence rationale, and a concise cause comparison.
4. Make the approval boundary visible beside the exact action, expected outcome, and verification checks.
5. Keep the approver decision explicit and separate; show execution and measured simulator verification as distinct steps.
6. End with a concise incident report and an honest benchmark/evaluation view.

Do not auto-approve or auto-execute for the sake of a video. Keep all interactions connected to real API state. Prefer an empty-state guided flow when no incidents exist over fabricated sample incidents.

## Verified demo facts
- The local first-run workspace contains 8 registered services. Read the count and health from the API; never substitute a larger illustrative count.
- A fresh workspace has no incidents, investigation runs, approval requests, or incident activity. Show a truthful empty state until the user starts a run.
- The first seeded case is `SCN-001`, titled `Peak traffic alert · Checkout API`. Its injected signal describes traffic rising before the first failed requests; investigation identifies database connection pool exhaustion.
- Label seeded runs as controlled local simulation. Do not imply production telemetry, live monitoring, generated activity, or automatic approval.
- Keep user-visible text at readable sizes: body 14px or more and supporting text 12px or more. All state must remain driven by the actual application data.
