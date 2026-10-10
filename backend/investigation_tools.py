"""Bounded, incident-scoped read tools shared by the workflow and MCP server."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import app as core
from backend import prometheus

MAX_RESULTS = 50
MAX_WINDOW = timedelta(days=7)


def _timestamp(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise core.ApiError(400, "invalid_time_range", name + " must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise core.ApiError(400, "invalid_time_range", name + " must be an ISO-8601 timestamp.")
    if parsed.tzinfo is None:
        raise core.ApiError(400, "invalid_time_range", name + " must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _context(incident_id: str):
    if not isinstance(incident_id, str) or not 4 <= len(incident_id) <= 80:
        raise core.ApiError(400, "invalid_incident_scope", "Provide a valid incident ID.")
    with core.db() as con:
        incident = con.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
        if not incident:
            raise core.ApiError(404, "incident_not_found", "Incident not found.")
        service_rows = con.execute("SELECT id,name,tier,owner,description,dependencies FROM services").fetchall()
        services = {row["id"]: {**dict(row), "dependencies": core.loads(row["dependencies"], [])} for row in service_rows}
        scenario = con.execute("SELECT * FROM scenarios WHERE id=?", (incident["scenario_id"],)).fetchone() if incident["scenario_id"] else None
        lab = con.execute("SELECT * FROM lab_runs WHERE incident_id=?", (incident_id,)).fetchone()
    scope, pending = set(), [incident["service_id"]]
    while pending and len(scope) < len(services):
        service_id = pending.pop()
        if service_id in scope or service_id not in services:
            continue
        scope.add(service_id)
        pending.extend(services[service_id]["dependencies"])
    return dict(incident), scenario, services, scope, dict(lab) if lab else None


def _scope(incident_id: str, service_id: str | None = None):
    incident, scenario, services, allowed, lab = _context(incident_id)
    selected = service_id or incident["service_id"]
    if selected not in allowed:
        raise core.ApiError(403, "service_scope_denied", "The requested service is outside this incident's dependency scope.")
    return incident, scenario, services, allowed, lab, selected


def _window(start_time: str | None, end_time: str | None):
    start, end = _timestamp(start_time, "start_time"), _timestamp(end_time, "end_time")
    if start and end and start > end:
        raise core.ApiError(400, "invalid_time_range", "start_time must not be after end_time.")
    current = datetime.now(timezone.utc)
    if (start and start > current) or (end and end > current):
        raise core.ApiError(400, "invalid_time_range", "Tool time ranges must not extend into the future.")
    lower, upper = start or end or current - MAX_WINDOW, end or current
    if upper - lower > MAX_WINDOW:
        raise core.ApiError(400, "time_range_too_large", "A tool query may span at most seven days.")
    return start, end


def _records(incident_id: str, kind: str, service_id: str | None, limit: int, start_time: str | None, end_time: str | None):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_RESULTS:
        raise core.ApiError(400, "invalid_limit", "limit must be between 1 and 50.")
    incident, scenario, services, allowed, _lab = _context(incident_id)
    selected = service_id
    if selected and selected not in allowed:
        raise core.ApiError(403, "service_scope_denied", "The requested service is outside this incident's dependency scope.")
    start, end = _window(start_time, end_time)
    records = []
    provider_enabled = False
    if scenario:
        observed_at = incident["created_at"]
        stamp = _timestamp(observed_at, "incident timestamp")
        if (start and stamp < start) or (end and stamp > end):
            return []
        for record_kind, source, observation, signal_id, severity in core.loads(scenario["plan"], []):
            if record_kind != kind:
                continue
            signal_service = core.SIGNAL_SERVICES.get(signal_id, incident["service_id"])
            if selected and selected != signal_service and selected != incident["service_id"] and selected not in source.casefold() and services[selected]["name"].casefold() not in source.casefold():
                continue
            records.append({"incident_id": incident_id, "correlation_id": incident["correlation_id"], "kind": kind,
                "service_id": signal_service, "source": source, "observation": observation, "signal_id": signal_id,
                "severity": severity, "observed_at": observed_at, "provenance": "seeded-local-scenario"})
        unavailable = [(source, message) for source, message in core.loads(scenario["errors"], []) if source == kind]
    else:
        with core.db() as con:
            rows = con.execute("SELECT payload FROM incident_observations WHERE incident_id=? AND kind=? ORDER BY observed_at DESC,rowid DESC",
                (incident_id,kind)).fetchall()
            has_observations = bool(rows) or bool(con.execute("SELECT 1 FROM incident_observations WHERE incident_id=? LIMIT 1",
                (incident_id,)).fetchone())
        observations = [core.loads(row["payload"], {}) for row in rows]
        for item in observations:
            if item.get("service_id") not in allowed or (selected and item.get("service_id") != selected):
                continue
            stamp = _timestamp(item.get("observed_at"), "observation timestamp")
            if (start and stamp < start) or (end and stamp > end):
                continue
            records.append(item)
        if kind == "metrics":
            provider_enabled = prometheus.enabled()
            records.extend(prometheus.collect(incident, selected, allowed, start, end))
        if not has_observations and not records and not provider_enabled:
            raise core.ApiError(503, "telemetry_unavailable", "No evidence has been submitted for this incident.")
        unavailable = []
    if unavailable:
        raise core.ApiError(503, "telemetry_unavailable", unavailable[0][1])
    return records[:limit]


def list_services(incident_id: str):
    incident, _scenario, services, allowed, lab = _context(incident_id)
    state = core.loads(lab["state_json"], {}) if lab else {}
    return {"incident_id": incident_id, "services": [{"id": key, "name": services[key]["name"], "tier": services[key]["tier"],
        "status": state.get("services", {}).get(key, {}).get("status", "healthy"), "dependencies": services[key]["dependencies"]}
        for key in sorted(allowed)]}


def get_service_health(incident_id: str, service_id: str):
    incident, _scenario, services, _allowed, lab, selected = _scope(incident_id, service_id)
    state = core.loads(lab["state_json"], {}) if lab else {}
    status = state.get("services", {}).get(selected, {}).get("status", "healthy")
    return {"incident_id": incident_id, "service_id": selected, "service_name": services[selected]["name"],
        "status": status, "observed_at": core.now(), "correlation_id": incident["correlation_id"], "source": "local-simulator"}


def get_service_dependencies(incident_id: str, service_id: str):
    _incident, _scenario, services, _allowed, _lab, selected = _scope(incident_id, service_id)
    return {"incident_id": incident_id, "service_id": selected, "dependencies": services[selected]["dependencies"], "source": "service-registry"}


def get_recent_logs(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None):
    return {"items": _records(incident_id, "logs", service_id, limit, start_time, end_time)}


def query_error_metrics(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None):
    return {"items": _records(incident_id, "metrics", service_id, limit, start_time, end_time)}


def get_request_traces(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None):
    return {"items": _records(incident_id, "traces", service_id, limit, start_time, end_time)}


def get_deployment_history(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None):
    return {"items": _records(incident_id, "changes", service_id, limit, start_time, end_time)}


def get_recent_config_changes(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None):
    return {"items": _records(incident_id, "changes", service_id, limit, start_time, end_time)}


def search_incident_runbooks(query: str, limit: int = 10):
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 200 or not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise core.ApiError(400, "invalid_runbook_query", "Provide a 2–200 character query and a limit from 1 to 20.")
    terms = set(query.casefold().split())
    matches = []
    for cause_id, cause in core.CAUSES.items():
        action = core.ACTION_CATALOG.get(cause_id)
        text = " ".join((cause[0], cause[1], cause[4], cause[5], cause[2])).casefold()
        score = sum(term in text for term in terms)
        if score:
            matches.append({"id": "RUN-" + cause_id, "title": cause[0], "service_id": cause[2], "steps": [cause[4], cause[5]],
                "sandbox_action": {"type": action[0], "service_id": action[1], "parameters": action[2]} if action else None,
                "provenance": "bundled-runbook"})
    matches.sort(key=lambda item: item["id"])
    return {"runbooks": matches[:limit]}


def compare_time_windows(incident_id: str, service_id: str | None = None, limit: int = 50):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_RESULTS:
        raise core.ApiError(400, "invalid_limit", "limit must be between 1 and 50.")
    incident, scenario, _services, _allowed, _lab, selected = _scope(incident_id, service_id)
    evidence = []
    for kind in ("logs", "metrics", "traces", "changes"):
        evidence.extend(_records(incident_id, kind, selected, min(limit, MAX_RESULTS), None, None))
    baselines = [item for item in evidence if "baseline" in item["observation"].casefold()]
    return {"incident_id": incident_id, "service_id": selected, "current_window": {"observed_at": incident["created_at"], "evidence_count": len(evidence), "observations": evidence[:MAX_RESULTS]},
        "baseline": {"available": bool(baselines), "observations": baselines, "provenance": "seeded-scenario-baseline" if scenario else "submitted-evidence"},
        "comparison_limit": "OpsPilot stores bounded incident observations, not continuous time-series data."}


TOOL_FUNCTIONS = {
    "list_services": list_services,
    "get_service_health": get_service_health,
    "get_recent_logs": get_recent_logs,
    "query_error_metrics": query_error_metrics,
    "get_request_traces": get_request_traces,
    "get_service_dependencies": get_service_dependencies,
    "get_deployment_history": get_deployment_history,
    "get_recent_config_changes": get_recent_config_changes,
    "search_incident_runbooks": search_incident_runbooks,
    "compare_time_windows": compare_time_windows,
}
