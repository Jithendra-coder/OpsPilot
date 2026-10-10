"""Local stdio MCP gateway. This server exposes observation tools only."""

from __future__ import annotations

import json

import app as core
from mcp.server import MCPServer

from backend import investigation_tools as tools

mcp = MCPServer("OpsPilot read-only observability tools")


def _json(function, *args, **kwargs):
    try:
        return json.dumps(function(*args, **kwargs), ensure_ascii=False, separators=(",", ":"))
    except core.ApiError as error:
        return json.dumps({"error": {"code": error.code, "message": error.message}}, separators=(",", ":"))


@mcp.tool()
def list_services(incident_id: str) -> str:
    """List the bounded service scope reachable from an incident."""
    return _json(tools.list_services, incident_id)


@mcp.tool()
def get_service_health(incident_id: str, service_id: str) -> str:
    """Read local simulator health for a service in the incident's dependency scope."""
    return _json(tools.get_service_health, incident_id, service_id)


@mcp.tool()
def get_recent_logs(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None) -> str:
    """Read at most 50 timestamped, incident-correlated log observations."""
    return _json(tools.get_recent_logs, incident_id, service_id, limit, start_time, end_time)


@mcp.tool()
def query_error_metrics(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None) -> str:
    """Read bounded error and health metrics for an incident time window."""
    return _json(tools.query_error_metrics, incident_id, service_id, limit, start_time, end_time)


@mcp.tool()
def get_request_traces(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None) -> str:
    """Read bounded request trace observations and their source identifiers."""
    return _json(tools.get_request_traces, incident_id, service_id, limit, start_time, end_time)


@mcp.tool()
def get_service_dependencies(incident_id: str, service_id: str) -> str:
    """Read registered downstream dependencies inside the incident's scope."""
    return _json(tools.get_service_dependencies, incident_id, service_id)


@mcp.tool()
def get_deployment_history(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None) -> str:
    """Read bounded deployment observations correlated with an incident."""
    return _json(tools.get_deployment_history, incident_id, service_id, limit, start_time, end_time)


@mcp.tool()
def get_recent_config_changes(incident_id: str, service_id: str | None = None, limit: int = 50, start_time: str | None = None, end_time: str | None = None) -> str:
    """Read bounded configuration-change observations correlated with an incident."""
    return _json(tools.get_recent_config_changes, incident_id, service_id, limit, start_time, end_time)


@mcp.tool()
def search_incident_runbooks(query: str, limit: int = 10) -> str:
    """Search the bundled, read-only incident runbook catalog."""
    return _json(tools.search_incident_runbooks, query, limit)


@mcp.tool()
def compare_time_windows(incident_id: str, service_id: str | None = None, limit: int = 50) -> str:
    """Compare seeded incident evidence with any explicit baseline observations."""
    return _json(tools.compare_time_windows, incident_id, service_id, limit)


if __name__ == "__main__":
    core.initialize()
    mcp.run(transport="stdio")
