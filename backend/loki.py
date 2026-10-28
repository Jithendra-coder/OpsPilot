"""Read bounded, service-scoped log matches from Grafana Loki."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

import app as core
from backend import provider_http

MAX_QUERIES = 25
MAX_RESULTS = 50
MAX_WINDOW = timedelta(days=7)


def enabled():
    return bool(os.environ.get("OPSPILOT_LOKI_URL", "").strip())


def configuration():
    try:
        url = provider_http.endpoint("OPSPILOT_LOKI_URL", "/loki/api/v1/query_range")
        if not url:
            return None
        raw = os.environ.get("OPSPILOT_LOKI_QUERIES", "")
        if len(raw) > 16 * 1024:
            raise ValueError("query configuration too long")
        queries = json.loads(raw)
        if not isinstance(queries, dict) or not 1 <= len(queries) <= MAX_QUERIES or any(
            signal not in core.SIGNAL_KINDS or core.SIGNAL_KINDS[signal] != "logs"
            or not isinstance(text, str) or not 1 <= len(text.strip()) <= 240 or "\n" in text or "\r" in text
            for signal, text in queries.items()
        ):
            raise ValueError("invalid query mapping")
        return url, queries, provider_http.bearer_token("OPSPILOT_LOKI_TOKEN")
    except (ValueError, TypeError, json.JSONDecodeError):
        raise core.ApiError(503, "loki_configuration", "Configure Loki signal IDs to bounded literal log filters and use an HTTPS or loopback URL.")


def _window(incident, start_time, end_time):
    current = datetime.now(timezone.utc)
    try:
        lower = datetime.fromisoformat(incident["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc) - timedelta(minutes=1)
    except (TypeError, ValueError, KeyError):
        raise core.ApiError(503, "loki_unavailable", "The incident time window is invalid for the configured log source.")
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
            for signal, text in queries.items():
                service = core.SIGNAL_SERVICES[signal]
                if service not in allowed or service_id and service != service_id:
                    continue
                if len(records) >= min(limit, MAX_RESULTS):
                    break
                query_limit = min(25, limit - len(records))
                query = "{service_name=" + json.dumps(service) + "} |= " + json.dumps(text.strip())
                result = provider_http.json_response(client, "GET", url, params={
                    "query": query,
                    "start": str(int(lower.timestamp() * 1_000_000_000)),
                    "end": str(int(upper.timestamp() * 1_000_000_000)),
                    "direction": "backward",
                    "limit": str(query_limit),
                }, token=token, deadline=deadline, source="Loki")
                if not isinstance(result, dict) or result.get("status") != "success" or not isinstance(result.get("data", {}).get("result"), list):
                    raise ValueError("invalid Loki query result")
                streams = result["data"]["result"]
                if len(streams) > query_limit:
                    raise ValueError("too many Loki streams")
                returned = 0
                for stream in streams:
                    if not isinstance(stream, dict) or not isinstance(stream.get("stream"), dict) or not isinstance(stream.get("values"), list):
                        raise ValueError("invalid Loki stream")
                    labels = stream["stream"]
                    if labels.get("service_name") != service:
                        returned += len(stream["values"])
                        if returned > query_limit:
                            raise ValueError("too many Loki log entries")
                        continue
                    for value in stream["values"]:
                        returned += 1
                        if returned > query_limit:
                            raise ValueError("too many Loki log entries")
                        if not isinstance(value, list) or len(value) != 2:
                            raise ValueError("invalid Loki log entry")
                        try:
                            stamp = datetime.fromtimestamp(int(value[0]) / 1_000_000_000, timezone.utc)
                        except (TypeError, ValueError, OverflowError, OSError):
                            raise ValueError("invalid Loki log timestamp")
                        if not lower <= stamp <= upper:
                            continue
                        records.append({"incident_id": incident["id"], "correlation_id": incident["correlation_id"],
                            "kind": "logs", "service_id": service, "source": "loki:" + signal,
                            "observation": "Configured Loki log filter matched.", "signal_id": signal,
                            "severity": "error", "observed_at": stamp.isoformat().replace("+00:00", "Z"),
                            "provenance": "loki-http-api"})
                        if len(records) >= min(limit, MAX_RESULTS):
                            break
                    if len(records) >= min(limit, MAX_RESULTS):
                        break
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        raise core.ApiError(503, "loki_unavailable", "The configured log source could not return valid incident evidence.")
    return records
