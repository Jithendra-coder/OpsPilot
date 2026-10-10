"use strict";

const state = {
  view: location.hash.replace("#", "") || "overview",
  overview: null,
  incidents: [],
  scenarios: [],
  selectedId: "",
  report: null,
  csrf: "",
  search: "",
  statusFilter: "",
  severityFilter: "",
  evaluation: null,
  approvals: [],
  user: "Local operator",
  role: "operator",
  busy: false
};

const icons = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="4" rx="1.5"/><rect x="14" y="10" width="7" height="11" rx="1.5"/><rect x="3" y="13" width="7" height="8" rx="1.5"/>',
  incidents: '<path d="M12 3 21 19H3L12 3Z"/><path d="M12 9v4"/><path d="M12 16h.01"/>',
  services: '<rect x="3" y="4" width="7" height="6" rx="1.5"/><rect x="14" y="14" width="7" height="6" rx="1.5"/><path d="M10 7h4v10h-4"/>',
  investigation: '<circle cx="10.8" cy="10.8" r="6.5"/><path d="m16 16 4.5 4.5"/><path d="m8.5 11 1.6 1.5 3-3.3"/>',
  lab: '<path d="M9 3h6"/><path d="M10 3v6.5l-5.2 8.7A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-2.8L14 9.5V3"/><path d="M7.5 16h9"/>',
  search: '<circle cx="10.8" cy="10.8" r="6.4"/><path d="m16 16 4.5 4.5"/>',
  arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12v7c0 1.7 3.6 3 8 3 1.7 0 3.4-.2 4.8-.7"/>',
  activity: '<path d="M3 12h4l3-8 4 15 3-7h4"/>',
  shield: '<path d="M12 22s8-3.8 8-10V5l-8-3-8 3v7c0 6.2 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  note: '<path d="M5 4h14a2 2 0 0 1 2 2v14l-4-3H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M7 9h10M7 13h7"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
  server: '<rect x="3" y="3" width="18" height="8" rx="2"/><rect x="3" y="13" width="18" height="8" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/>',
  spark: '<path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-2-5.8L4 11l6-2.2L12 3Z"/><path d="m19 15 .9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z"/>',
  eye: '<path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.7"/>',
  eyeOff: '<path d="m3 3 18 18M10.6 6.2A9.9 9.9 0 0 1 12 6c6.1 0 9.5 6 9.5 6a14 14 0 0 1-3 3.5M6.2 6.4C3.8 8 2.5 12 2.5 12s3.4 6 9.5 6c1.1 0 2.1-.2 3-.5"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>'
};

function icon(name, className) {
  return '<svg class="' + (className || "") + '" viewBox="0 0 24 24" aria-hidden="true">' + (icons[name] || icons.activity) + "</svg>";
}

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
  });
}

function dateLabel(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

function ageLabel(value) {
  if (!value) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
  if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
  return Math.floor(seconds / 86400) + "d ago";
}

function severityMark(value) {
  const severity = ["P1", "P2", "P3", "P4"].includes(value) ? value.toLowerCase() : "p3";
  return '<span class="severity-mark ' + severity + '" aria-label="' + esc(value) + '"></span>';
}

function statePill(value) {
  const safe = String(value || "NEW").toUpperCase();
  const label = safe.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, function (char) { return char.toUpperCase(); });
  return '<span class="state-pill ' + safe.toLowerCase() + '"><span class="status-dot"></span>' + esc(label) + "</span>";
}

function severityPill(value) {
  return '<span class="severity-pill">' + severityMark(value) + esc(value) + "</span>";
}

async function api(path, options) {
  const settings = options || {};
  const headers = new Headers(settings.headers || {});
  if (settings.body) headers.set("Content-Type", "application/json");
  if (settings.method && settings.method !== "GET" && path !== "/api/v1/auth/session") headers.set("X-CSRF-Token", state.csrf);
  const response = await fetch(path, Object.assign({ credentials: "same-origin" }, settings, { headers: headers }));
  const data = await response.json().catch(function () { return {}; });
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/v1/auth/session") showAuth();
    const error = new Error(data.error && data.error.message || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function showAuth() {
  state.csrf = "";
  document.getElementById("auth-screen").hidden = false;
  document.getElementById("app-shell").hidden = true;
}

function showApp() {
  document.getElementById("auth-screen").hidden = true;
  document.getElementById("app-shell").hidden = false;
}

function toast(message, isError) {
  const region = document.getElementById("toast-region");
  const item = document.createElement("div");
  item.className = "toast" + (isError ? " error" : "");
  item.innerHTML = '<span class="toast-icon" aria-hidden="true">' + (isError ? "!" : "✓") + "</span><span>" + esc(message) + "</span>";
  region.appendChild(item);
  window.setTimeout(function () { item.remove(); }, 3400);
}

function serviceName(id) {
  const services = state.overview ? state.overview.services : [];
  const service = services.find(function (item) { return item.id === id; });
  return service ? service.name : id || "—";
}

function pageTitle(view) {
  return { overview: "Incident command", incidents: "Incidents", services: "Service map", investigation: "Investigation", approvals: "Approval center", lab: "Replay lab" }[view] || "Incident command";
}

async function refresh() {
  const results = await Promise.all([api("/api/v1/overview"), api("/api/v1/incidents?limit=50"), api("/api/v1/scenarios"), api("/api/v1/approvals?status=all")]);
  state.overview = results[0];
  state.incidents = results[1].incidents;
  state.scenarios = results[2].scenarios;
  state.approvals = results[3].approvals;
  document.getElementById("nav-open-count").textContent = state.overview.stats.open_incidents;
  document.getElementById("nav-approval-count").textContent = state.approvals.filter(function (item) { return item.approval_status === "pending"; }).length;
  document.getElementById("create-incident-top").hidden = state.role !== "operator";
  document.getElementById("profile-name").textContent = state.user;
  document.getElementById("profile-role").textContent = state.role === "approver" ? "Independent approver" : "Operator";
  if (state.selectedId) {
    try { state.report = (await api("/api/v1/incidents/" + encodeURIComponent(state.selectedId) + "/report")).report; }
    catch (error) { state.report = null; state.selectedId = ""; }
  }
  render();
}

function render() {
  if (!state.overview) return;
  const view = ["overview", "incidents", "services", "investigation", "approvals", "lab"].includes(state.view) ? state.view : "overview";
  state.view = view;
  const createIncidentButton = document.getElementById("create-incident-top");
  createIncidentButton.classList.toggle("button-primary", view !== "overview");
  createIncidentButton.classList.toggle("button-quiet", view === "overview");
  document.querySelectorAll("[data-nav]").forEach(function (button) { button.classList.toggle("active", button.dataset.nav === view); });
  document.getElementById("breadcrumb-current").textContent = pageTitle(view);
  const page = document.getElementById("page-content");
  page.innerHTML = view === "overview" ? renderOverview() :
    view === "incidents" ? renderIncidents() :
        view === "services" ? renderServices() :
        view === "investigation" ? renderInvestigation() :
          view === "approvals" ? renderApprovals() : renderLab();
}

function heading(title, description, actions, extraClass) {
  return '<div class="page-heading' + (extraClass ? " " + extraClass : "") + '"><div><h1>' + esc(title) + '</h1><p>' + esc(description) + '</p></div><div class="heading-actions">' + (actions || "") + "</div></div>";
}

function stat(label, value, foot, kind, iconName) {
  return '<section class="card stat-card"><div class="stat-top"><span>' + esc(label) + '</span><span class="stat-icon ' + (kind || "") + '">' + icon(iconName) + '</span></div><div class="stat-value">' + esc(value) + '</div><div class="stat-foot">' + foot + "</div></section>";
}

function incidentRows(items, compact) {
  if (!items.length) return '<div class="empty-state"><span class="empty-icon">' + icon("check") + '</span><strong>All clear for now</strong>No active incidents need attention.</div>';
  return '<div class="incident-list">' + items.slice(0, compact ? 5 : items.length).map(function (incident) {
    return '<button class="incident-row" data-action="open-incident" data-id="' + esc(incident.id) + '"><span class="incident-main">' +
      severityMark(incident.severity) + '<span class="incident-copy"><strong class="incident-title">' + esc(incident.title) +
      '</strong><span class="incident-subline"><span>' + esc(incident.id) + '</span><span class="sub-sep">·</span><span>' +
      esc(serviceName(incident.service_id)) + '</span><span class="sub-sep">·</span><span>' + esc(incident.owner) +
      '</span></span></span></span><span class="incident-meta">' + statePill(incident.status) +
      '<span class="incident-age">' + esc(ageLabel(incident.updated_at)) + "</span></span></button>";
  }).join("") + "</div>";
}

function serviceLines(services) {
  return '<div class="service-summary">' + services.slice(0, 6).map(function (service) {
    return '<div class="service-line"><span class="service-avatar">' + icon(service.id === "postgres" ? "database" : "server") +
      '</span><span class="service-line-copy"><strong>' + esc(service.name) + '</strong><small>' + esc(service.tier) + " · " + esc(service.owner) +
      '</small></span><span class="service-health ' + (service.status === "degraded" ? "degraded" : "") +
      '"><span class="status-dot"></span>' + (service.status === "degraded" ? "Issue" : "Healthy") + "</span></div>";
  }).join("") + "</div>";
}

function activityList(events) {
  if (!events.length) return '<div class="empty-state activity-empty"><span class="empty-icon">' + icon("clock") + '</span><strong>No incident activity yet</strong>Start the guided incident to see real investigation, approval, and verification events recorded here.</div>';
  return '<div class="activity-list">' + events.slice(0, 5).map(function (event) {
    const label = event.kind.replaceAll(".", " ").replaceAll("_", " ");
    return '<div class="activity-row"><span class="activity-icon">' + icon(event.kind.indexOf("investigation") >= 0 ? "investigation" : "activity") +
      '</span><span class="activity-copy"><strong>' + esc(event.incident_title) + '</strong><span>' + esc(label) + " · " + esc(event.service_id) +
      '</span></span><span class="activity-time">' + esc(ageLabel(event.created_at)) + "</span></div>";
  }).join("") + "</div>";
}

function renderOverview() {
  const data = state.overview;
  const open = data.incidents.filter(function (item) { return ["RESOLVED", "FAILED"].indexOf(item.status) < 0; });
  const high = open.filter(function (item) { return item.severity === "P1"; }).length;
  const pendingApprovals = state.approvals.filter(function (item) { return item.approval_status === "pending"; }).length;
  const guidedScenario = state.scenarios.find(function (item) { return item.id === "SCN-001"; });
  const activeGuidedIncident = data.incidents.find(function (item) {
    return item.scenario_id === "SCN-001" && ["NEW", "TRIAGING", "INVESTIGATING", "AWAITING_APPROVAL", "REMEDIATING", "VERIFYING"].includes(item.status);
  });
  const metrics = [
    stat("Open incidents", data.stats.open_incidents, '<span class="' + (data.stats.open_incidents ? "trend-up" : "trend-good") + '">' + (data.stats.open_incidents ? esc(data.stats.open_incidents + " require attention") : "No active incidents") + "</span>", data.stats.open_incidents ? "red" : "", "incidents"),
    stat("Critical · P1", high, high ? '<span class="trend-up">Immediate attention</span>' : "No critical incidents", high ? "red" : "", "activity"),
    stat("Healthy services", data.stats.healthy_services + "/" + data.stats.services, '<span class="trend-good">' + esc(data.stats.services - data.stats.healthy_services) + " degraded</span>", "blue", "server"),
    stat("Pending approvals", pendingApprovals, pendingApprovals ? '<span class="trend-up">Independent review needed</span>' : "No actions awaiting review", pendingApprovals ? "amber" : "", "shield")
  ].join("");
  const steps = [
    ["Signal", guidedScenario ? guidedScenario.description : "The guided scenario is unavailable in this workspace."],
    ["Investigate", "Read-only logs, metrics, and traces scoped to this incident."],
    ["Approve", "A second role reviews the exact allowlisted action."],
    ["Verify", "Server-side checks must pass before the incident resolves."]
  ].map(function (step, index) {
    return '<li class="command-step"><span class="command-step-number" aria-hidden="true">' + (index + 1) + '</span><div><strong>' + esc(step[0]) + '</strong><p>' + esc(step[1]) + "</p>" +
      (index === 2 ? '<span class="approval-gate">' + icon("shield") + " Independent approval gate</span>" : "") + "</div></li>";
  }).join("");
  const disabled = state.busy || (!activeGuidedIncident && (state.role !== "operator" || !guidedScenario));
  const runLabel = state.busy ? '<span class="spinner"></span> ' + (activeGuidedIncident ? "Opening incident…" : "Starting incident…") : activeGuidedIncident ? "Continue guided incident" : state.role !== "operator" ? "Operator role required" : !guidedScenario ? "Scenario unavailable" : "Run guided incident";
  const guidedAction = activeGuidedIncident ? "open-incident" : "replay";
  const guidedIncidentId = activeGuidedIncident ? activeGuidedIncident.id : guidedScenario ? guidedScenario.id : "";
  const guidedActionLabel = activeGuidedIncident ? "Continue guided incident: " : "Run guided incident: ";
  const guidedStatus = activeGuidedIncident ? "Incident in progress" : !guidedScenario ? "Unavailable" : state.role !== "operator" ? "Operator role required" : "Ready to launch";
  return heading("Incident command", "Investigate with evidence. Require independent approval before remediation.",
    '<span class="command-environment"><span class="status-dot"></span> GUIDED CASE</span>', "command-heading") +
    '<section class="command-workspace" aria-label="Guided incident workspace"><div class="command-journey card"><div class="command-panel-heading"><p class="eyebrow">THE RESPONSE PATH</p><h2>From signal to verified recovery</h2><p>Every stage is visible. Remediation stays behind an independent approval.</p></div><ol class="command-steps">' + steps +
    '</ol></div><div class="command-launch"><div class="command-launch-top"><span class="scenario-label">GUIDED SCENARIO · ' + esc(guidedScenario ? guidedScenario.id : "SCN-001") + '</span><span class="ready-label"><span class="status-dot"></span>' + esc(guidedStatus) + '</span></div>' +
    '<p class="eyebrow">' + esc(guidedScenario ? serviceName(guidedScenario.service_id) : "EXAMPLE CASE") + '</p><h2>' + esc(guidedScenario ? guidedScenario.title : "Guided scenario unavailable") + '</h2><p class="command-description">Follow the incident from its first signal through correlated evidence, a supported diagnosis, a human-reviewed fix, and server-verified recovery.</p>' +
    '<div class="command-actions"><button class="button button-primary command-run" data-action="' + guidedAction + '" data-id="' + esc(guidedIncidentId) + '" aria-label="' + esc(guidedActionLabel + (guidedScenario ? guidedScenario.title : "scenario unavailable")) + '" ' + (disabled ? "disabled" : "") + '>' + runLabel + ' ' + (state.busy ? "" : icon("arrow")) + '</button><button class="button command-secondary" data-nav="lab">Explore all scenarios ' + icon("arrow") + '</button></div>' +
    '<p class="command-safety">' + icon("shield") + '<span>Investigation is read-only. Any replay action needs separate approval.</span></p></div></section>' +
    '<section class="stats-grid command-stats" aria-label="Current workspace status">' + metrics + '</section>' +
    '<div class="overview-grid command-support"><section class="card panel"><div class="section-head panel-head"><div><h2>Recent activity</h2><p>Incident decisions and outcomes recorded in this workspace</p></div><button class="text-link" data-nav="incidents">Incident history ' + icon("arrow") + "</button></div>" + activityList(data.activity) +
    '</section><section class="card panel"><div class="section-head panel-head"><div><h2>Service baseline</h2><p>' + esc(data.stats.healthy_services) + " of " + esc(data.stats.services) + ' services healthy</p></div><button class="text-link" data-nav="services">Service map ' + icon("arrow") + "</button></div>" +
    serviceLines(data.services) + '<div class="panel-footer"><span>Showing ' + Math.min(6, data.services.length) + ' of ' + esc(data.stats.services) + ' services · Current workspace</span><span class="small-meta">Registered services</span></div></section></div>';
}

function renderIncidents() {
  const shown = state.incidents.filter(function (item) {
    return (!state.search || (item.title + " " + item.id + " " + item.description).toLowerCase().includes(state.search.toLowerCase())) &&
      (!state.statusFilter || item.status === state.statusFilter) && (!state.severityFilter || item.severity === state.severityFilter);
  });
  const table = shown.length ? '<table class="incident-table"><thead><tr><th>INCIDENT</th><th>SEVERITY</th><th>STATUS</th><th>SERVICE</th><th>OWNER</th><th>UPDATED</th></tr></thead><tbody>' +
    shown.map(function (item) { return '<tr data-action="open-incident" data-id="' + esc(item.id) + '"><td><span class="table-incident">' + severityMark(item.severity) +
      '<span class="table-incident-copy"><strong>' + esc(item.title) + '</strong><small>' + esc(item.id) + "</small></span></span></td><td>" + severityPill(item.severity) +
      "</td><td>" + statePill(item.status) + '</td><td class="table-cell-muted">' + esc(serviceName(item.service_id)) + '</td><td class="table-cell-muted">' + esc(item.owner) +
      '</td><td class="table-cell-muted">' + esc(ageLabel(item.updated_at)) + "</td></tr>"; }).join("") + "</tbody></table>" :
    '<div class="empty-state"><span class="empty-icon">' + icon("incidents") + '</span><strong>No incidents match</strong>Try another filter or create an incident.</div>';
  return heading("Incidents", "Triage alerts, review investigation findings, and keep the incident history in one place.",
    '<button class="button button-primary button-compact" data-action="new-incident"><span class="plus">+</span> Create incident</button>') +
    '<section class="card"><div class="table-toolbar"><div class="toolbar-left"><label class="search-wrap">' + icon("search") + '<input id="incident-search" type="search" value="' + esc(state.search) + '" placeholder="Search incidents" aria-label="Search incidents"></label></div>' +
    '<div class="toolbar-right"><select class="compact-select" id="severity-filter" aria-label="Filter by severity"><option value="">All severities</option>' +
    ["P1", "P2", "P3", "P4"].map(function (x) { return '<option value="' + x + '"' + (state.severityFilter === x ? " selected" : "") + ">" + x + "</option>"; }).join("") +
    '</select><select class="compact-select" id="status-filter" aria-label="Filter by status"><option value="">All statuses</option>' +
    ["NEW","TRIAGING","INVESTIGATING","AWAITING_APPROVAL","REMEDIATING","VERIFYING","RESOLVED","ESCALATED","FAILED"].map(function (x) { return '<option value="' + x + '"' + (state.statusFilter === x ? " selected" : "") + ">" + x.replaceAll("_"," ") + "</option>"; }).join("") +
    "</select></div></div>" + table + '<div class="table-footer"><span>Showing ' + esc(shown.length) + " of " + esc(state.incidents.length) + ' incidents</span><span class="filter-count">Up to 50 incidents</span></div></section>';
}

function renderServices() {
  const groups = ["Edge", "Core", "Data", "Worker"];
  const services = state.overview.services;
  const grid = groups.map(function (tier) {
    const items = services.filter(function (service) { return service.tier === tier; });
    if (!items.length) return "";
    return '<div class="map-column"><p class="map-group-label">' + esc(tier) + "</p>" + items.map(function (service) {
      const dependencies = service.dependencies.length ? "→ " + service.dependencies.map(serviceName).join(", ") : "No downstream services";
      return '<div class="service-node ' + (service.status === "degraded" ? "degraded" : "") + '"><span class="node-health"></span><span class="service-avatar">' +
        icon(service.id === "postgres" ? "database" : "server") + '</span><span class="service-node-copy"><strong>' + esc(service.name) + '</strong><small>' +
        esc(service.owner) + " · " + esc(dependencies) + "</small></span></div>";
    }).join("") + "</div>";
  }).join("");
  const table = services.map(function (service) {
    return '<div class="service-line"><span class="service-avatar">' + icon(service.id === "postgres" ? "database" : "server") +
      '</span><span class="service-line-copy"><strong>' + esc(service.name) + '</strong><small>' + esc(service.description) +
      '</small></span><span class="service-health ' + (service.status === "degraded" ? "degraded" : "") + '"><span class="status-dot"></span>' +
      (service.status === "degraded" ? "Degraded" : "Healthy") + "</span></div>";
  }).join("");
  return heading("Service map", "A clear view of registered services and their direct dependencies.") +
    '<section class="card service-map"><div class="section-head"><div><h2 class="section-title">Application topology</h2><p class="muted">Each service lists its registered downstream dependencies.</p></div><span class="small-meta"><span class="status-dot dot-green"></span>' +
    esc(services.length) + ' registered services</span></div><div class="map-stage">' + grid + '</div><div class="topology-key"><span><i class="status-dot dot-green"></i> Healthy</span><span><i class="severity-mark p2"></i> Degraded by an open incident</span><span>→ Depends on</span></div>' +
    '<p class="dependency-note">Dependencies are displayed from the service registry.</p></section>' +
    '<section class="card panel services-detail-panel"><div class="section-head panel-head"><div><h2>Registered services</h2><p>Ownership and current incident signal</p></div></div>' + table + "</section>";
}

function openIncidents() {
  return state.incidents.filter(function (item) { return ["RESOLVED", "FAILED"].indexOf(item.status) < 0; });
}

function renderInvestigation() {
  if (!state.selectedId) {
    const open = openIncidents();
    if (!open.length) return heading("Investigation", "Evidence, hypotheses, and findings for one incident.") +
      '<section class="card panel"><div class="empty-state"><span class="empty-icon">' + icon("investigation") + '</span><strong>No incident selected</strong>Create an incident or launch a replay scenario to begin.<p><button class="button button-primary" data-nav="lab">Open replay lab</button></p></div></section>';
    state.selectedId = open[0].id;
    const id = state.selectedId;
    api("/api/v1/incidents/" + encodeURIComponent(id) + "/report").then(function (data) {
      if (state.selectedId === id) { state.report = data.report; render(); }
    }).catch(function (error) { toast(error.message, true); });
    return '<div class="loading-state"><span class="spinner" aria-label="Loading incident"></span></div>';
  }
  if (!state.report) return '<div class="loading-state"><span class="spinner" aria-label="Loading incident"></span></div>';
  const report = state.report;
  const incident = report.incident;
  const result = report.investigation && report.investigation.result;
  const remediation = report.remediation || [];
  const latestAction = report.investigation ? remediation.find(function (item) { return item.investigation_id === report.investigation.id; }) : null;
  const actionButtons = '<button class="button button-compact" data-action="export-report">' + icon("download") + " Export report</button>" +
    (["NEW","TRIAGING","INVESTIGATING"].includes(incident.status) ? '<button class="button button-compact" data-action="escalate-incident">Escalate</button>' : "") +
    (incident.status === "ESCALATED" ? '<button class="button button-compact" data-action="retriage-incident">Return to triage</button>' : "") +
    (incident.source === "simulation" && incident.status === "NEW" && !report.investigation && state.role === "operator" ? '<button class="button button-compact" data-action="reset-simulation">Reset replay</button>' : "");
  const choices = state.incidents.filter(function (x) { return ["RESOLVED","FAILED"].indexOf(x.status) < 0; }).map(function (x) {
    return '<option value="' + esc(x.id) + '"' + (x.id === state.selectedId ? " selected" : "") + ">" + esc(x.id + " · " + x.title) + "</option>";
  }).join("");
  const selection = choices ? '<select class="compact-select" id="investigation-select" aria-label="Choose incident">' + choices + "</select>" : "";
  const facts = '<div class="incident-facts"><span class="fact"><span class="fact-label">Service</span><span class="fact-value">' + esc(serviceName(incident.service_id)) +
    '</span></span><span class="fact"><span class="fact-label">Owner</span><span class="fact-value">' + esc(incident.owner) +
    '</span></span><span class="fact"><span class="fact-label">Created</span><span class="fact-value">' + esc(dateLabel(incident.created_at)) +
    '</span></span><span class="fact"><span class="fact-label">Correlation ID</span><span class="fact-value">' + esc(incident.correlation_id) + "</span></span></div>";
  const steps = ["Gather context", "Collect evidence", "Compare causes", "Report findings"].map(function (name, i) {
    return '<span class="run-step ' + (result ? "done" : "") + '"><span class="step-dot">' + (result ? icon("check") : (i + 1)) + "</span>" + esc(name) + "</span>";
  }).join("");
  const canInvestigate = state.role === "operator" && (["NEW", "TRIAGING", "INVESTIGATING", "ESCALATED"].includes(incident.status) ||
    (incident.status === "AWAITING_APPROVAL" && latestAction && latestAction.approval_status === "expired"));
  const runLabel = result ? "Run again" : "Start investigation";
  const runBlock = '<div class="run-intro"><span class="run-intro-copy"><strong>' + (result ? "Read-only investigation complete" : "Ready to investigate") +
    '</strong><span>' + (result ? "Evidence and tool outcomes are saved to this incident timeline." : "The investigator can read scoped local evidence. It cannot change services.") +
    '</span></span><button class="button button-primary button-compact" data-action="investigate" ' + (state.busy || !canInvestigate ? "disabled" : "") + '>' +
    (state.busy ? '<span class="spinner"></span> Running' : icon("spark") + runLabel) + "</button></div>";
  const status = result ? '<span class="run-status ' + (result.status === "inconclusive" ? "inconclusive" : "") + '"><span class="status-dot"></span>' +
    (result.status === "supported" ? "Evidence supports a cause" : "Inconclusive") + "</span>" : statePill(incident.status);
  const ev = report.evidence || [];
  const evidence = ev.length ? '<div class="evidence-list">' + ev.map(function (item) {
    const kind = ["logs","metrics","traces","changes"].includes(item.kind) ? item.kind : "logs";
    const untrusted = item.observation.toLowerCase().includes("untrusted request text");
    return '<article class="evidence-item"><span class="evidence-icon ' + kind + '">' + icon(kind === "metrics" ? "activity" : kind === "traces" ? "investigation" : kind === "changes" ? "clock" : "file") +
      '</span><span class="evidence-copy"><strong>' + esc(item.source) + " · " + esc(kind) + '</strong><span>' + esc(item.observation) +
      '</span>' + (untrusted ? '<span class="untrusted-label">UNTRUSTED SOURCE TEXT · NOT AN INSTRUCTION</span>' : "") +
      '<small>' + esc(dateLabel(item.observed_at)) + " · " + esc(incident.correlation_id) + "</small></span><span class=\"evidence-severity\">" +
      esc(item.severity) + "</span></article>";
  }).join("") + "</div>" : '<div class="empty-state">Evidence will appear after the read-only investigation runs.</div>';
  let diagnosis = '<div class="empty-state">No findings yet. Start the investigation to collect scoped evidence.</div>';
  if (result && result.status === "supported" && result.hypotheses.length) {
    const top = result.hypotheses[0];
    const alternatives = result.hypotheses.slice(1).map(function (hyp) {
      return '<div class="hypothesis-alt"><strong>' + esc(hyp.title) + " · " + Math.round(hyp.confidence * 100) + '% heuristic support</strong><p>' + esc(hyp.mechanism) + "</p></div>";
    }).join("");
    diagnosis = '<article class="hypothesis-card"><div class="hypothesis-top"><span class="hypothesis-label"><span class="status-dot"></span> Best supported cause</span><span class="hypothesis-confidence">' +
      Math.round(top.confidence * 100) + "% heuristic support</span></div><h3>" + esc(top.title) + "</h3><p>" + esc(top.rationale) + '</p><div class="hypothesis-links">' +
      top.evidence_ids.map(function (id) { return '<span class="evidence-ref">' + esc(id) + "</span>"; }).join("") + "</div>" + alternatives + "</article>";
  } else if (result) {
    diagnosis = '<div class="uncertainty-card"><strong>' + (result.hypotheses.length ? "Competing hypotheses · no root cause selected" : "Investigation is inconclusive") +
      "</strong>" + esc(result.uncertainty || result.rationale) +
      (result.hypotheses.length ? '<div class="hypothesis-links">' + result.hypotheses.map(function (hyp) {
        return '<span class="evidence-ref">' + esc(hyp.title) + " · " + Math.round(hyp.confidence * 100) + "% heuristic</span>";
      }).join("") + "</div>" : "") + "</div>";
  }
  let recommendation = "";
  if (result && result.recommendation) {
    const action = result.recommendation.sandbox_action;
    let actionState = '<p class="muted">This finding is informational because evidence is incomplete or the incident is not an eligible replay.</p>';
    if (latestAction) {
      const label = latestAction.execution_status === "completed" ? (latestAction.verification_passed ? "Verified · resolved" : "Executed · verification failed") :
        latestAction.approval_status === "pending" ? "Waiting for independent approval" : latestAction.approval_status === "approved" ? "Approved · ready to execute" :
          latestAction.approval_status === "rejected" ? "Rejected · investigate again before proposing" : latestAction.approval_status;
      actionState = '<div class="approval-state"><strong>' + esc(label) + '</strong><span>Proposal ' + esc(latestAction.id) + " · approval expires " + esc(dateLabel(latestAction.expires_at)) + '</span><button class="text-link" data-nav="approvals">Open approval center ' + icon("arrow") + "</button></div>";
    } else if (action && state.role === "operator" && incident.source === "simulation" && incident.status === "INVESTIGATING") {
      actionState = '<p class="muted">Exact action: <code>' + esc(action.type) + '</code> on <code>' + esc(action.service_id) + '</code>. An independent approver must approve its immutable parameters before it can run.</p><button class="button button-primary button-compact" data-action="propose-remediation">Request approval</button>';
    }
    recommendation = '<section class="recommendation-card"><div class="recommendation-title">' + icon("spark") + " Recommended next step</div><p>" +
      esc(result.recommendation.summary) + "</p>" + actionState + '<div class="safe-boundary">' + icon("shield") +
      "<span>Only the predeclared action is available. Server-side health and symptom checks control resolution.</span></div></section>";
  }
  const timelineEvents = (report.timeline || []).map(function (item) {
    return { label: item.kind, status: "", detail: item.details.reason || item.details.note || "", created_at: item.created_at };
  }).concat((report.tool_timeline || []).map(function (item) {
    return { label: item.stage, status: item.status, detail: item.details.result_count + " result(s) · " + (item.details.note || item.details.reason || "recorded"), created_at: item.created_at };
  })).sort(function (a, b) { return a.created_at.localeCompare(b.created_at); });
  const timeline = timelineEvents.length ? '<div class="timeline-mini">' + timelineEvents.slice(-12).reverse().map(function (event) {
    const summary = event.label.replaceAll(":", " ").replaceAll(".", " ").replaceAll("_", " ");
    const detail = event.status ? event.status + " · " + event.detail : event.detail;
    return '<div class="timeline-item"><span class="timeline-dot">' + icon(event.label.indexOf("investigation") >= 0 || event.label.indexOf("tool:") === 0 ? "investigation" : "check") +
      '</span><span class="timeline-copy"><strong>' + esc(summary) + '</strong><small>' + esc(dateLabel(event.created_at)) +
      (detail ? " · " + esc(detail) : "") + "</small></span></div>";
  }).join("") + "</div>" : '<div class="empty-state">No events recorded yet.</div>';
  const notes = report.comments || [];
  const noteList = notes.length ? '<div class="timeline-mini">' + notes.slice(-3).reverse().map(function (note) {
    return '<div class="timeline-item"><span class="timeline-dot">' + icon("note") + '</span><span class="timeline-copy"><strong>' + esc(note.actor) +
      '</strong><small>' + esc(note.body) + " · " + esc(dateLabel(note.created_at)) + "</small></span></div>";
  }).join("") + "</div>" : "";
  return heading("Investigation workspace", "Observations stay distinct from hypotheses. Every finding links back to its evidence.",
    selection + actionButtons) +
    '<section class="card incident-hero"><div class="incident-hero-top"><div><div class="incident-idline">' + severityMark(incident.severity) + esc(incident.id) +
    '<span>·</span>' + esc(incident.source === "simulation" ? "Replay" : incident.source.replaceAll("_"," ")) + "</div><h2>" + esc(incident.title) + '</h2><p>' + esc(incident.description) +
    "</p></div>" + status + "</div>" + facts + "</section>" +
    '<div class="workspace-layout"><div><section class="card investigation-panel"><div class="section-head"><div><h2>Investigation run</h2><p>Bounded, read-only tools · deterministic evidence matching</p></div>' +
    (result ? '<span class="small-meta">' + esc(dateLabel(report.investigation.completed_at)) + "</span>" : "") + "</div>" +
    '<div class="run-steps">' + steps + "</div>" + runBlock +
    '<div class="evidence-section"><div class="section-head"><div><h2>Observed evidence</h2><p>Source and incident correlation are preserved</p></div><span class="small-meta">' + esc(ev.length) + " records</span></div>" +
    evidence + "</div>" +
    '<div class="evidence-section"><div class="section-head"><div><h2>Root-cause hypotheses</h2><p>Interpretations supported by the observations above</p></div></div>' +
    '<div class="diagnosis-body">' + diagnosis + "</div>" + recommendation + "</div></section>" +
    '<section class="card panel investigation-detail-panel"><div class="section-head panel-head"><div><h2>Investigation timeline</h2><p>Status and operator notes</p></div><span class="small-meta">AUDIT LOG</span></div>' + timeline + noteList +
    '<form class="note-form" id="comment-form"><textarea name="body" aria-label="Incident note" placeholder="Add an investigation note…" maxlength="1200" required></textarea><button class="button" type="submit">' + icon("note") + " Add note</button></form></section></div>" +
    '<aside class="workspace-side"><section class="card side-panel"><div class="section-head"><h2>Incident details</h2></div><div class="side-kv"><div class="side-kv-row"><span>Incident status</span><strong>' + esc(incident.status.replaceAll("_"," ")) +
    '</strong></div><div class="side-kv-row"><span>Severity</span><strong>' + esc(incident.severity) +
    '</strong></div><div class="side-kv-row"><span>Service</span><strong>' + esc(serviceName(incident.service_id)) +
    '</strong></div><div class="side-kv-row"><span>Owner</span><strong>' + esc(incident.owner) +
    '</strong></div><div class="side-kv-row"><span>Scenario</span><strong>' + (incident.scenario_id ? "Replay lab" : "Manual intake") + "</strong></div></div></section>" +
    '<section class="card side-panel"><div class="section-head"><h2>Timeline</h2><button class="text-link" data-action="export-report">' + icon("download") + "</button></div>" + timeline +
    '</section><section class="card side-panel"><div class="section-head"><h2>Action controls</h2></div><div class="safe-boundary">' + icon("shield") +
    "<span>Changes use allowlisted actions, require independent approval, and need server-side verification.</span></div></section></aside></div>";
}

function renderApprovals() {
  const pending = state.approvals.filter(function (item) { return item.approval_status === "pending"; }).length;
  const cards = state.approvals.map(function (item) {
    const parameters = JSON.stringify(item.parameters, null, 2);
    const guidance = [["Expected result", item.expected_result], ["Verification", item.verification],
      ["Prerequisites", (item.prerequisites || []).join(" ")], ["Rollback", item.rollback]].filter(function (entry) { return entry[1]; });
    const guidanceHtml = guidance.length ? '<div class="approval-guidance">' + guidance.map(function (entry) {
      return '<div><span>' + esc(entry[0]) + '</span><strong>' + esc(entry[1]) + '</strong></div>';
    }).join("") + "</div>" : "";
    let controls = '<span class="small-meta">' + esc(item.approval_status.replaceAll("_", " ")) + " · " + esc(dateLabel(item.expires_at)) + "</span>";
    if (item.approval_status === "pending" && state.role === "approver") {
      controls = item.proposed_by === state.user ? '<span class="form-hint">You cannot approve your own proposal.</span>' :
        '<div class="approval-actions"><button class="button button-primary button-compact" data-action="approval-approve" data-id="' + esc(item.approval_id) + '">Approve action</button><button class="button button-compact" data-action="approval-reject" data-id="' + esc(item.approval_id) + '">Reject</button></div>';
    } else if (item.approval_status === "approved" && !item.execution_id && state.role === "operator" && item.approved_by !== state.user) {
      controls = '<button class="button button-primary button-compact" data-action="execute-approved" data-id="' + esc(item.proposal_id) + '">Run approved change</button>';
    } else if (item.execution_status === "completed") {
      controls = '<span class="run-status ' + (item.verification_passed ? "" : "inconclusive") + '"><span class="status-dot"></span>' +
        (item.verification_passed ? "Verified · incident resolved" : "Verification failed · incident remains open") + "</span>";
    } else if (item.approval_status === "pending" && state.role !== "approver") {
      controls = '<span class="form-hint">Independent approver sign-in required.</span>';
    } else if (item.approval_status === "approved" && state.role === "approver") {
      controls = '<span class="form-hint">Approved by ' + esc(item.approved_by || "approver") + ' · operator execution pending.</span>';
    }
    return '<article class="card approval-card"><div class="approval-card-head"><div><span class="eyebrow">' + esc(item.incident_id) + " · " + esc(item.severity) +
      '</span><h2>' + esc(item.incident_title) + '</h2></div>' + statePill(item.incident_status) + '</div><p>' + esc(item.reason) + '</p><div class="approval-action"><span class="fact-label">ALLOWLISTED ACTION</span><strong>' +
      esc(item.action_type) + ' · ' + esc(item.service_id) + '</strong><pre>' + esc(parameters) + '</pre></div>' + guidanceHtml + '<div class="approval-meta"><span>Risk <strong>' + esc(item.risk) + '</strong></span><span>Proposed by <strong>' + esc(item.proposed_by) +
      '</strong></span><span>Expires <strong>' + esc(dateLabel(item.expires_at)) + '</strong></span></div><div class="approval-footer">' + controls +
      '<button class="text-link" data-action="open-incident" data-id="' + esc(item.incident_id) + '">View incident ' + icon("arrow") + "</button></div></article>";
  }).join("");
  return heading("Approval center", pending + " pending · approvals are tied to exact action parameters.", state.role === "approver" ? '<span class="small-meta">SIGNED IN AS INDEPENDENT APPROVER</span>' : '<span class="small-meta">OPERATOR · READ AND EXECUTE APPROVED ACTIONS</span>') +
    (cards || '<section class="card panel"><div class="empty-state"><strong>No remediation proposals</strong>Evidence-backed proposals will appear here after an investigation.</div></section>');
}

function renderLab() {
  const cards = state.scenarios.map(function (scenario) {
    return '<article class="scenario-card"><div class="scenario-card-head">' + severityPill(scenario.severity) + '<span class="tag difficulty-' + esc(scenario.difficulty) + '">' + esc(scenario.difficulty) +
      '</span></div><h3>' + esc(scenario.title) + '</h3><p>' + esc(scenario.description) + '</p><div class="scenario-card-footer"><span class="small-meta">' + esc(serviceName(scenario.service_id)) +
      '</span><button class="button scenario-run" data-action="replay" data-id="' + esc(scenario.id) + '" ' + (state.role !== "operator" ? "disabled" : "") + '>Replay ' + icon("arrow") + "</button></div></article>";
  }).join("");
  let evaluation = "";
  if (state.evaluation) {
    const summary = state.evaluation.report.summary;
    evaluation = '<div class="evaluation-result"><div class="eval-metric"><strong>' + Math.round(summary.accuracy * 100) + '%</strong><span>Catalog case match rate</span></div><div class="eval-metric"><strong>' +
      esc(summary.inconclusive) + "</strong><span>Appropriate inconclusive results</span></div></div><div class=\"eval-list\">" +
      state.evaluation.report.cases.slice(0, 8).map(function (item) { return '<div class="eval-case"><span>' + esc(item.title) + '</span><strong class="' + (item.correct ? "pass" : item.inconclusive ? "" : "fail") +
      '">' + (item.correct ? "Matched" : item.inconclusive ? "Inconclusive" : "Review") + "</strong></div>"; }).join("") +
      '<button class="button evaluation-export" data-action="export-evaluation">Download full JSON results ' + icon("download") + "</button>" +
      '<span class="small-meta evaluation-foot">' + esc(summary.scenario_count) + " scenarios · complete results are saved to the evaluation report</span></div>";
  }
  return heading("Replay lab", "Start a fault scenario, follow the investigation, and review its action proposal.",
    '<span class="eyebrow-inline">' + esc(state.scenarios.length) + " SCENARIOS</span>") +
    '<div class="lab-grid"><section class="card panel"><div class="section-head panel-head"><div><h2>Scenario library</h2><p>Includes incomplete, conflicting, and untrusted evidence cases</p></div><span class="small-meta">READY TO REPLAY</span></div><div class="scenario-grid">' + cards +
    '</div></section><div><section class="card evaluation-card"><p class="eyebrow">REPRODUCIBLE RULE CHECK</p><h2>Check the signature rules.</h2><p>Run the catalog cases through the deterministic engine and inspect matches and inconclusive outcomes.</p><p class="small-meta">Cases reuse internal rule IDs, so this is a consistency check, not an accuracy test.</p>' +
    '<button class="button" data-action="evaluate" ' + (state.busy || state.role !== "operator" ? "disabled" : "") + '>' + (state.busy ? '<span class="spinner"></span> Evaluating…' : icon("activity") + " Run full evaluation (" + state.scenarios.length + ")") + "</button>" + evaluation +
    '</section><div class="method-note">' + icon("shield") + '<span><strong>Safe by design.</strong> Investigation is read-only. Actions require a supported finding, independent approval, idempotent execution, and server-side recovery checks.</span></div></div></div>';
}

function modal(content) {
  const dialog = document.getElementById("modal");
  document.getElementById("modal-panel").innerHTML = content;
  if (!dialog.open) dialog.showModal();
}

function closeModal() {
  const dialog = document.getElementById("modal");
  if (dialog.open) dialog.close();
}

function newIncidentModal() {
  const services = state.overview.services.map(function (service) { return '<option value="' + esc(service.id) + '">' + esc(service.name) + "</option>"; }).join("");
  modal('<div class="modal-head"><div><h2>Create incident</h2><p>Capture the signal and assign a service owner.</p></div><button class="icon-button modal-close" data-action="close-modal" aria-label="Close">' + icon("close") + "</button></div>" +
    '<form class="modal-form" id="new-incident-form"><div class="field"><label for="new-title">Incident title</label><input id="new-title" name="title" minlength="8" maxlength="120" placeholder="e.g. Checkout error rate is rising" required></div>' +
    '<div class="field-row"><div class="field"><label for="new-severity">Severity</label><select id="new-severity" name="severity"><option>P1</option><option selected>P2</option><option>P3</option><option>P4</option></select></div><div class="field"><label for="new-service">Affected service</label><select id="new-service" name="service_id">' + services + "</select></div></div>" +
    '<div class="field"><label for="new-owner">Owner</label><input id="new-owner" name="owner" maxlength="80" value="Local operator" required></div><div class="field"><label for="new-description">What are you seeing?</label><textarea id="new-description" name="description" minlength="8" maxlength="1200" placeholder="Include the alert, time window, and observed symptoms." required></textarea><span class="field-hint">Operational input is treated as untrusted evidence.</span></div>' +
    '<div class="modal-actions"><button class="button" type="button" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit">Create incident</button></div></form>');
}

function approvalDecisionModal(id, decision) {
  const label = decision === "approve" ? "Approve replay action" : "Reject proposal";
  const prompt = decision === "approve" ? "Your approval is bound to the exact action type and parameters shown in the approval center." : "Record why the proposed action should not proceed.";
  modal('<div class="modal-head"><div><h2>' + label + '</h2><p>' + prompt + '</p></div><button class="icon-button modal-close" data-action="close-modal" aria-label="Close">' + icon("close") + "</button></div>" +
    '<form class="modal-form" id="approval-decision-form" data-id="' + esc(id) + '" data-decision="' + esc(decision) + '"><div class="field"><label for="approval-note">Decision note</label><textarea id="approval-note" name="note" minlength="6" maxlength="500" placeholder="Explain the decision for the audit trail." required></textarea></div>' +
    (decision === "approve" ? '<label class="check-row"><input type="checkbox" required><span>I reviewed the exact action and confirm it is safe for this replay.</span></label>' : "") +
    '<div class="modal-actions"><button class="button" type="button" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit">' + label + "</button></div></form>");
}

function executionModal(proposalId) {
  const item = state.approvals.find(function (approval) { return approval.proposal_id === proposalId; });
  if (!item) return;
  modal('<div class="modal-head"><div><h2>Execute approved action</h2><p>This applies the approved change to the incident replay state.</p></div><button class="icon-button modal-close" data-action="close-modal" aria-label="Close">' + icon("close") + "</button></div>" +
    '<div class="approval-action"><span class="fact-label">APPROVED ACTION</span><strong>' + esc(item.action_type) + " · " + esc(item.service_id) + '</strong><pre>' + esc(JSON.stringify(item.parameters, null, 2)) + '</pre><small>Approved by ' + esc(item.approved_by || "independent reviewer") + '</small></div>' +
    '<form class="modal-form" id="action-execute-form" data-id="' + esc(proposalId) + '"><label class="check-row"><input type="checkbox" required><span>Apply the change to this incident’s replay state and verify it.</span></label><div class="modal-actions"><button class="button" type="button" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit">Execute and verify</button></div></form>');
}

function escalationModal(retriage) {
  const title = retriage ? "Return incident to triage" : "Escalate incident";
  const button = retriage ? "Return to triage" : "Escalate incident";
  modal('<div class="modal-head"><div><h2>' + title + '</h2><p>Record why this needs a different investigation path.</p></div><button class="icon-button modal-close" data-action="close-modal" aria-label="Close">' + icon("close") + "</button></div>" +
    '<form class="modal-form" id="escalation-form" data-retriage="' + String(retriage) + '"><div class="field"><label for="escalation-note">Operator note</label><textarea id="escalation-note" name="note" minlength="6" maxlength="500" placeholder="Describe the missing evidence or next owner." required></textarea></div>' +
    '<div class="modal-actions"><button class="button" type="button" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit">' + button + "</button></div></form>");
}

function exportReport() {
  if (!state.report) return;
  const data = JSON.stringify(state.report, null, 2);
  const blob = new Blob([data], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = state.report.incident.id.toLowerCase() + "-report.json";
  link.click();
  window.setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
  toast("Incident report exported.");
}

function exportEvaluation() {
  if (!state.evaluation) return;
  const blob = new Blob([JSON.stringify(state.evaluation.report, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = state.evaluation.id.toLowerCase() + "-evaluation.json";
  link.click();
  window.setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
  toast("Full evaluation results exported.");
}

async function openIncident(id) {
  state.selectedId = id;
  state.view = "investigation";
  state.report = null;
  render();
  history.replaceState(null, "", "#investigation");
  try {
    state.report = (await api("/api/v1/incidents/" + encodeURIComponent(id) + "/report")).report;
    render();
  } catch (error) { toast(error.message, true); }
}

async function replay(id) {
  state.busy = true;
  render();
  try {
    const result = await api("/api/v1/simulations/start", { method: "POST", body: JSON.stringify({ scenario_id: id }) });
    await refresh();
    await openIncident(result.incident.id);
    toast("Replay scenario started.");
  } catch (error) { state.busy = false; render(); toast(error.message, true); }
  finally { state.busy = false; render(); }
}

async function startInvestigation() {
  if (!state.selectedId || state.busy) return;
  state.busy = true;
  render();
  try {
    await api("/api/v1/incidents/" + encodeURIComponent(state.selectedId) + "/investigate", {
      method: "POST", body: JSON.stringify({ idempotency_key: crypto.randomUUID() })
    });
    await refresh();
    toast("Read-only investigation completed.");
  } catch (error) { toast(error.message, true); }
  finally { state.busy = false; render(); }
}

async function proposeRemediation() {
  if (!state.selectedId || state.busy) return;
  state.busy = true; render();
  try {
    await api("/api/v1/incidents/" + encodeURIComponent(state.selectedId) + "/remediation/propose", { method: "POST", body: "{}" });
    await refresh();
    toast("Proposal submitted for independent approval.");
  } catch (error) { toast(error.message, true); }
  finally { state.busy = false; render(); }
}

async function executeApproved(proposalId) {
  state.busy = true; closeModal(); render();
  try {
    const result = await api("/api/v1/actions/" + encodeURIComponent(proposalId) + "/execute", {
      method: "POST", body: JSON.stringify({ idempotency_key: crypto.randomUUID() })
    });
    await refresh();
    await openIncident(result.execution.incident_id || (state.approvals.find(function (item) { return item.proposal_id === proposalId; }) || {}).incident_id);
    toast(result.verification.passed ? "Action verified; incident resolved." : "Action ran, but verification did not pass.", !result.verification.passed);
  } catch (error) { toast(error.message, true); }
  finally { state.busy = false; render(); }
}

async function runEvaluation() {
  if (state.busy) return;
  state.busy = true;
  render();
  try {
    const result = await api("/api/v1/evaluations", { method: "POST", body: "{}" });
    state.evaluation = result.evaluation;
    render();
    toast("Benchmark completed across " + result.evaluation.case_count + " scenarios.");
  } catch (error) { toast(error.message, true); }
  finally { state.busy = false; render(); }
}

async function loadSession() {
  try {
    const session = await api("/api/v1/auth/session");
    state.csrf = session.csrf_token;
    state.user = session.user;
    state.role = session.role;
    showApp();
    await refresh();
  } catch (_) { showAuth(); }
}

document.getElementById("login-form").addEventListener("submit", async function (event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  const error = document.getElementById("login-error");
  error.textContent = "";
  button.disabled = true;
  try {
    const result = await api("/api/v1/auth/session", { method: "POST", body: JSON.stringify({ password: document.getElementById("login-password").value }) });
    state.csrf = result.csrf_token;
    state.user = result.user;
    state.role = result.role;
    document.getElementById("login-password").value = "";
    showApp();
    await refresh();
  } catch (failure) { error.textContent = failure.message; }
  finally { button.disabled = false; }
});

document.getElementById("toggle-password").addEventListener("click", function () {
  const field = document.getElementById("login-password");
  const visible = field.type === "password";
  field.type = visible ? "text" : "password";
  this.setAttribute("aria-label", visible ? "Hide password" : "Show password");
  this.title = visible ? "Hide password" : "Show password";
  this.innerHTML = icon(visible ? "eyeOff" : "eye");
});

document.getElementById("create-incident-top").addEventListener("click", newIncidentModal);
document.getElementById("signout-button").addEventListener("click", async function () {
  try { await api("/api/v1/auth/session", { method: "DELETE" }); } catch (_) {}
  showAuth();
  document.getElementById("login-password").focus();
});

document.addEventListener("click", async function (event) {
  const nav = event.target.closest("[data-nav]");
  if (nav) {
    event.preventDefault();
    state.view = nav.dataset.nav;
    history.replaceState(null, "", "#" + state.view);
    render();
    document.getElementById("page-content").focus({ preventScroll: true });
    return;
  }
  const action = event.target.closest("[data-action]");
  if (!action) return;
  switch (action.dataset.action) {
    case "new-incident": newIncidentModal(); break;
    case "close-modal": closeModal(); break;
    case "open-incident": await openIncident(action.dataset.id); break;
    case "replay": await replay(action.dataset.id); break;
    case "investigate": await startInvestigation(); break;
    case "evaluate": await runEvaluation(); break;
    case "propose-remediation": await proposeRemediation(); break;
    case "reset-simulation":
      try {
        await api("/api/v1/simulations/" + encodeURIComponent(state.selectedId) + "/reset", { method: "POST", body: "{}" });
        await refresh(); toast("The isolated replay returned to its healthy baseline.");
      } catch (error) { toast(error.message, true); }
      break;
    case "approval-approve": approvalDecisionModal(action.dataset.id, "approve"); break;
    case "approval-reject": approvalDecisionModal(action.dataset.id, "reject"); break;
    case "execute-approved": executionModal(action.dataset.id); break;
    case "escalate-incident": escalationModal(false); break;
    case "retriage-incident": escalationModal(true); break;
    case "export-report": exportReport(); break;
    case "export-evaluation": exportEvaluation(); break;
  }
});

document.getElementById("modal").addEventListener("click", function (event) {
  if (event.target === this) closeModal();
});

document.addEventListener("change", function (event) {
  if (event.target.id === "severity-filter") { state.severityFilter = event.target.value; render(); }
  if (event.target.id === "status-filter") { state.statusFilter = event.target.value; render(); }
  if (event.target.id === "investigation-select") openIncident(event.target.value);
});

document.addEventListener("input", function (event) {
  if (event.target.id === "incident-search") {
    const start = event.target.selectionStart;
    state.search = event.target.value;
    render();
    const input = document.getElementById("incident-search");
    input.focus();
    input.setSelectionRange(start, start);
  }
});

document.addEventListener("submit", async function (event) {
  if (event.target.id === "new-incident-form") {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target).entries());
    try {
      const result = await api("/api/v1/incidents", { method: "POST", body: JSON.stringify(data) });
      closeModal();
      await refresh();
      await openIncident(result.incident.id);
      toast("Incident created.");
    } catch (error) { toast(error.message, true); }
  }
  if (event.target.id === "approval-decision-form") {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target).entries());
    const decision = event.target.dataset.decision;
    try {
      await api("/api/v1/approvals/" + encodeURIComponent(event.target.dataset.id) + "/" + decision, { method: "POST", body: JSON.stringify({ note: data.note }) });
      closeModal(); await refresh();
      toast(decision === "approve" ? "Action approved. An operator can execute it." : "Proposal rejected and recorded.");
    } catch (error) { toast(error.message, true); }
  }
  if (event.target.id === "action-execute-form") {
    event.preventDefault();
    await executeApproved(event.target.dataset.id);
  }
  if (event.target.id === "escalation-form") {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target).entries());
    const target = event.target.dataset.retriage === "true" ? "TRIAGING" : "ESCALATED";
    try {
      await api("/api/v1/incidents/" + encodeURIComponent(state.selectedId) + "/status", {
        method: "POST", body: JSON.stringify({ status: target, note: data.note })
      });
      closeModal();
      await refresh();
      toast(target === "ESCALATED" ? "Incident escalated with an audit note." : "Incident returned to triage.");
    } catch (error) { toast(error.message, true); }
  }
  if (event.target.id === "comment-form") {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target).entries());
    try {
      await api("/api/v1/incidents/" + encodeURIComponent(state.selectedId) + "/comments", { method: "POST", body: JSON.stringify(data) });
      await refresh();
      toast("Investigation note added.");
    } catch (error) { toast(error.message, true); }
  }
});

loadSession();
