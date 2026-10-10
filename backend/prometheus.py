"""Read bounded, pre-mapped incident signals from the Prometheus HTTP API."""

from __future__ import annotations

import ipaddress
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

import app as core

MAX_RESPONSE = 1024 * 1024
MAX_QUERIES = 25
MAX_SAMPLES = 25
MAX_QUERY_SECONDS = 15


def enabled():
    return bool(os.environ.get("OPSPILOT_PROMETHEUS_URL", "").strip())


def configuration():
    base = os.environ.get("OPSPILOT_PROMETHEUS_URL", "").strip().rstrip("/")
    if not base:
        return None
    parsed = urlsplit(base)
    url_invalid = len(base) > 2048
    hostname = parsed.hostname or ""
    try:
        parsed.port
    except ValueError:
        url_invalid = True
    try:
        is_loopback = hostname.casefold() == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = hostname.casefold() == "localhost"
    if url_invalid or (parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback)) or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or ".." in parsed.path.split("/"):
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
    token = os.environ.get("OPSPILOT_PROMETHEUS_TOKEN", "").strip()
    if len(token) > 4096:
        raise core.ApiError(503, "prometheus_configuration", "The Prometheus bearer token is too long.")
    return base + "/api/v1/query_range", queries, token


def _read_response(client, url, query, start, end, token, deadline):
    headers = {"Authorization": "Bearer " + token} if token else {}
    step = max(60, math.ceil((end - start).total_seconds() / MAX_SAMPLES))
    try:
        timeout = min(5, deadline - time.monotonic())
        if timeout <= 0:
            raise ValueError("Prometheus query budget expired.")
        with client.stream("POST", url, data={"query": query, "start": str(start.timestamp()),
            "end": str(end.timestamp()), "step": str(step), "limit": "1"}, headers=headers, timeout=timeout) as response:
            if response.status_code != 200:
                raise ValueError("Prometheus returned a non-success status.")
            body = bytearray()
            for chunk in response.iter_bytes(64 * 1024):
                if time.monotonic() > deadline:
                    raise ValueError("Prometheus query budget expired.")
                body.extend(chunk)
                if len(body) > MAX_RESPONSE:
                    raise ValueError("Prometheus response exceeded its size limit.")
        result = json.loads(body)
        if result.get("status") != "success" or result.get("data", {}).get("resultType") != "matrix":
            raise ValueError("Prometheus returned an invalid query result.")
        series = result["data"].get("result")
        if not isinstance(series, list) or len(series) > 1:
            raise ValueError("Prometheus returned too many time series.")
        return series
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")


def collect(incident, service_id, allowed, start_time=None, end_time=None, *, transport=None):
    config = configuration()
    if not config:
        return []
    url, queries, token = config
    current = datetime.now(timezone.utc)
    lower = datetime.fromisoformat(incident["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
    lower = max(lower, current - timedelta(days=7))
    upper = current
    if start_time:
        lower = max(lower, start_time)
    if end_time:
        upper = min(upper, end_time)
    if lower > upper:
        return []
    client_options = {"timeout": 5, "follow_redirects": False, "trust_env": False}
    if transport:
        client_options["transport"] = transport
    records = []
    deadline = time.monotonic() + MAX_QUERY_SECONDS
    try:
        with httpx.Client(**client_options) as client:
            for signal, query in queries.items():
                service = core.SIGNAL_SERVICES[signal]
                if service not in allowed or service_id and service != service_id:
                    continue
                for item in _read_response(client, url, query, lower, upper, token, deadline):
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
    except httpx.HTTPError:
        raise core.ApiError(503, "prometheus_unavailable", "The configured metrics source could not return valid incident evidence.")
    records.sort(key=lambda item: item["observed_at"], reverse=True)
    return records[:50]
