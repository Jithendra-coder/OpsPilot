"""Read bounded, incident-scoped trace matches from Grafana Tempo."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from math import isfinite

import httpx

import app as core
from backend import provider_http

MAX_QUERIES = 25
MAX_RESULTS = 50
MAX_WINDOW = timedelta(days=7)
_TRACEQL_CONDITION = re.compile(r'(?:span|resource)\.[A-Za-z_][A-Za-z0-9_.]*\s*(?:=|!=)\s*(?:"[^"\r\n]{1,160}"|[0-9]{1,12}|true|false)\Z')


def enabled():
    return bool(os.environ.get("OPSPILOT_TEMPO_URL", "").strip())


def configuration():
    try:
        url = provider_http.endpoint("OPSPILOT_TEMPO_URL", "/api/search")
        if not url:
            return None
        raw = os.environ.get("OPSPILOT_TEMPO_QUERIES", "")
        if len(raw) > 16 * 1024:
            raise ValueError("query configuration too long")
        queries = json.loads(raw)
        if not isinstance(queries, dict) or not 1 <= len(queries) <= MAX_QUERIES or any(
            signal not in core.SIGNAL_KINDS or core.SIGNAL_KINDS[signal] != "traces"
            or not isinstance(condition, str) or not _TRACEQL_CONDITION.fullmatch(condition.strip())
            for signal, condition in queries.items()
        ):
            raise ValueError("invalid query mapping")
        return url, queries, provider_http.bearer_token("OPSPILOT_TEMPO_TOKEN")
    except (ValueError, TypeError, json.JSONDecodeError):
        raise core.ApiError(503, "tempo_configuration", "Configure Tempo signal IDs to bounded TraceQL attribute comparisons and use an HTTPS or loopback URL.")


def _window(incident, start_time, end_time):
    current = datetime.now(timezone.utc)
    try:
        lower = datetime.fromisoformat(incident["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc) - timedelta(minutes=1)
    except (TypeError, ValueError, KeyError):
        raise core.ApiError(503, "tempo_unavailable", "The incident time window is invalid for the configured trace source.")
    lower = max(lower, current - MAX_WINDOW)
    upper = current
    if start_time:
        lower = max(lower, start_time)
    if end_time:
        upper = min(upper, end_time)
    return lower, upper


def collect(incident, service_id, allowed, start_time=None, end_time=None, *, limit=MAX_RESULTS, transport=None):
    config = configuration()
    if not config or limit <= 0:
        return []
    url, queries, token = config
    lower, upper = _window(incident, start_time, end_time)
    if lower > upper:
        return []
    deadline = time.monotonic() + 15
    records = []
    try:
        with httpx.Client(**provider_http.client_options(transport)) as client:
            for signal, condition in queries.items():
                service = core.SIGNAL_SERVICES[signal]
                if service not in allowed or service_id and service != service_id:
                    continue
                if len(records) >= min(limit, MAX_RESULTS):
                    break
                query = "{ resource.service.name = " + json.dumps(service) + " && " + condition.strip() + " }"
                result = provider_http.json_response(client, "GET", url, params={
                    "q": query,
                    "start": str(int(lower.timestamp())),
                    "end": str(int(upper.timestamp())),
                    "limit": str(min(25, limit - len(records))),
                }, token=token, deadline=deadline, source="Tempo")
                if not isinstance(result, dict) or not isinstance(result.get("traces"), list):
                    raise ValueError("invalid Tempo search result")
                traces = result["traces"]
                if len(traces) > min(25, limit - len(records)):
                    raise ValueError("too many Tempo traces")
                for trace in traces:
                    if not isinstance(trace, dict) or not re.fullmatch(r"[0-9a-fA-F]{32}", str(trace.get("traceID", ""))):
                        raise ValueError("invalid Tempo trace")
                    try:
                        stamp = datetime.fromtimestamp(int(trace["startTimeUnixNano"]) / 1_000_000_000, timezone.utc)
                        spans = trace.get("spanSet", {}).get("spans", [])
                        duration = float(trace["durationMs"]) if "durationMs" in trace else float(spans[0]["durationNanos"]) / 1_000_000
                    except (KeyError, IndexError, TypeError, ValueError, OverflowError, OSError):
                        raise ValueError("invalid Tempo trace fields")
                    if not isfinite(duration) or duration < 0:
                        raise ValueError("invalid Tempo trace duration")
                    if not lower <= stamp <= upper:
                        continue
                    records.append({"incident_id": incident["id"], "correlation_id": incident["correlation_id"],
                        "kind": "traces", "service_id": service, "source": "tempo:" + signal,
                        "observation": "Configured Tempo trace condition matched; duration " + str(round(duration, 3)) + " ms.",
                        "signal_id": signal, "severity": "error", "observed_at": stamp.isoformat().replace("+00:00", "Z"),
                        "provenance": "tempo-search-api", "trace_id": trace["traceID"]})
                    if len(records) >= min(limit, MAX_RESULTS):
                        break
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        raise core.ApiError(503, "tempo_unavailable", "The configured trace source could not return valid incident evidence.")
    return records
