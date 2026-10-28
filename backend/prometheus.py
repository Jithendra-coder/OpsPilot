"""Read bounded, pre-mapped incident signals from the Prometheus HTTP API."""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

import app as core
from backend import provider_http

MAX_RESPONSE = 1024 * 1024
MAX_QUERIES = 25
MAX_SAMPLES = 25
MAX_QUERY_SECONDS = 15


def enabled():
    return bool(os.environ.get("OPSPILOT_PROMETHEUS_URL", "").strip())


def configuration():
    try:
        url = provider_http.endpoint("OPSPILOT_PROMETHEUS_URL", "/api/v1/query_range")
        if not url:
            return None
    except ValueError:
        raise core.ApiError(503, "prometheus_configuration", "The configured Prometheus URL must use HTTPS or a loopback HTTP address.")
    try:
        raw = os.environ.get("OPSPILOT_PROMETHEUS_QUERIES", "")
        if len(raw) > 16 * 1024:
            raise ValueError("query configuration too long")
        queries = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise core.ApiError(503, "prometheus_configuration", "Configure Prometheus signal queries as a JSON object.")
    if not isinstance(queries, dict) or not 1 <= len(queries) <= MAX_QUERIES or any(
        signal not in core.SIGNAL_KINDS or core.SIGNAL_KINDS[signal] != "metrics"
        or not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000
        for signal, query in queries.items()
    ):
        raise core.ApiError(503, "prometheus_configuration", "Prometheus queries must map supported metric signal IDs to bounded PromQL expressions.")
    try:
        token = provider_http.bearer_token("OPSPILOT_PROMETHEUS_TOKEN")
    except ValueError:
        raise core.ApiError(503, "prometheus_configuration", "The Prometheus bearer token is too long.")
    return url, queries, token


def _read_response(client, url, query, start, end, token, deadline):
    step = max(60, math.ceil((end - start).total_seconds() / MAX_SAMPLES))
    try:
        result = provider_http.json_response(client, "POST", url, data={"query": query, "start": str(start.timestamp()),
            "end": str(end.timestamp()), "step": str(step), "limit": "1"}, token=token,
            deadline=deadline, source="Prometheus")
        if result.get("status") != "success" or result.get("data", {}).get("resultType") != "matrix":
            raise ValueError("Prometheus returned an invalid query result.")
        series = result["data"].get("result")
        if not isinstance(series, list) or len(series) > 1:
            raise ValueError("Prometheus returned too many time series.")
        return series
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")


def collect(incident, service_id, allowed, start_time=None, end_time=None, *, limit=MAX_SAMPLES, transport=None):
    config = configuration()
    if not config or limit <= 0:
        return []
    url, queries, token = config
    current = datetime.now(timezone.utc)
    lower = datetime.fromisoformat(incident["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc) - timedelta(minutes=1)
    lower = max(lower, current - timedelta(days=7))
    upper = current
    if start_time:
        lower = max(lower, start_time)
    if end_time:
        upper = min(upper, end_time)
    if lower > upper:
        return []
    records = []
    deadline = time.monotonic() + MAX_QUERY_SECONDS
    try:
        with httpx.Client(**provider_http.client_options(transport)) as client:
            for signal, query in queries.items():
                service = core.SIGNAL_SERVICES[signal]
                if service not in allowed or service_id and service != service_id:
                    continue
                for item in _read_response(client, url, query, lower, upper, token, deadline):
                    if len(records) >= min(limit, MAX_SAMPLES * MAX_QUERIES):
                        break
                    if not isinstance(item, dict):
                        raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
                    labels = item.get("metric", {})
                    if not isinstance(labels, dict):
                        raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
                    if labels.get("service_id") and labels["service_id"] != service:
                        continue
                    values = item.get("values")
                    if not isinstance(values, list) or len(values) > MAX_SAMPLES:
                        raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
                    for sample in values:
                        if not isinstance(sample, list) or len(sample) != 2:
                            raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
                        try:
                            epoch, value = float(sample[0]), float(sample[1])
                            observed = datetime.fromtimestamp(epoch, timezone.utc)
                        except (TypeError, ValueError, IndexError, OverflowError, OSError):
                            raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
                        if not math.isfinite(epoch) or not math.isfinite(value):
                            raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
                        if not lower <= observed <= upper:
                            continue
                        records.append({"incident_id": incident["id"], "correlation_id": incident["correlation_id"],
                            "kind": "metrics", "service_id": service, "source": "prometheus:" + signal,
                            "observation": "Configured PromQL signal matched at value " + str(value),
                            "signal_id": signal, "severity": "warning", "observed_at": observed.isoformat().replace("+00:00", "Z"),
                            "provenance": "prometheus-http-api"})
                        if len(records) >= min(limit, MAX_SAMPLES * MAX_QUERIES):
                            break
    except httpx.HTTPError:
        raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
    records.sort(key=lambda item: item["observed_at"], reverse=True)
    return records[:min(limit, MAX_SAMPLES * MAX_QUERIES)]
