"""Normalize the Alertmanager webhook contract without trusting its labels."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import app as core

SEVERITY = {"critical": "P1", "error": "P1", "warning": "P2", "info": "P3", "debug": "P4"}


def _timestamp(value, name):
    if not isinstance(value, str):
        raise core.ApiError(400, "invalid_alertmanager_payload", name + " must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise core.ApiError(400, "invalid_alertmanager_payload", name + " must be an ISO-8601 timestamp.")
    if parsed.tzinfo is None:
        raise core.ApiError(400, "invalid_alertmanager_payload", name + " must include a timezone.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > datetime.now(timezone.utc):
        raise core.ApiError(400, "invalid_alertmanager_payload", name + " must not be in the future.")
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_group(payload):
    alerts = payload.get("alerts") if isinstance(payload, dict) else None
    if not isinstance(alerts, list) or len(alerts) > core.MAX_OBSERVATIONS:
        raise core.ApiError(400, "invalid_alertmanager_payload", "The Alertmanager payload must contain between 0 and 25 alerts.")
    normalized = {"firing": [], "resolved": []}
    for alert in alerts:
        if not isinstance(alert, dict) or alert.get("status") not in normalized:
            raise core.ApiError(400, "invalid_alertmanager_payload", "Each Alertmanager alert must have firing or resolved status.")
        labels, annotations = alert.get("labels"), alert.get("annotations", {})
        if not isinstance(labels, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in labels.items()):
            raise core.ApiError(400, "invalid_alertmanager_payload", "Alert labels must be a string map.")
        if not isinstance(annotations, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in annotations.items()):
            raise core.ApiError(400, "invalid_alertmanager_payload", "Alert annotations must be a string map.")
        fingerprint = core.text_field(alert.get("fingerprint"), "fingerprint", 4, 128)
        started = _timestamp(alert.get("startsAt"), "startsAt")
        correlation = "am-" + hashlib.sha256((fingerprint + "\0" + started).encode()).hexdigest()[:48]
        item = {"fingerprint": fingerprint, "correlation_id": correlation, "starts_at": started}
        if alert["status"] == "resolved":
            ended = alert.get("endsAt")
            item["ends_at"] = _timestamp(ended, "endsAt") if ended else core.now()
        else:
            service = core.text_field(labels.get("service_id"), "service_id", 1, 60)
            raw_title = annotations.get("summary") or labels.get("alertname") or ("Alert on " + service)
            title = core.text_field(raw_title, "summary", 1, 120)
            if len(title) < 8:
                title = core.text_field("Alert: " + title, "summary", 8, 120)
            description = annotations.get("description") or title
            if len(description.strip()) < 8:
                description = title
            raw_severity = labels.get("severity", "warning").strip().casefold()
            severity = raw_severity.upper() if raw_severity.upper() in {"P1", "P2", "P3", "P4"} else SEVERITY.get(raw_severity, "P2")
            item.update({"title": title, "severity": severity, "service_id": service,
                "description": core.text_field(description, "description", 8, 1200),
                "owner": core.text_field(labels.get("owner", "Unassigned"), "owner", 1, 80),
                "evidence": []})
        normalized[alert["status"]].append(item)
    return normalized
