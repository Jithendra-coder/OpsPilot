"""Shared network limits for configured read-only telemetry providers."""

from __future__ import annotations

import ipaddress
import json
import os
import time
from urllib.parse import unquote, urlsplit

import httpx

MAX_RESPONSE = 1024 * 1024
REQUEST_SECONDS = 5


def endpoint(variable: str, suffix: str) -> str | None:
    base = os.environ.get(variable, "").strip().rstrip("/")
    if not base:
        return None
    try:
        parsed = urlsplit(base)
        parsed.port
        host = parsed.hostname or ""
        try:
            loopback = host.casefold() == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host.casefold() == "localhost"
        allowed_http_hosts = {item.strip().casefold() for item in os.environ.get("OPSPILOT_PROVIDER_HTTP_HOSTS", "").split(",") if item.strip()}
        internal_http = host.casefold() in allowed_http_hosts
    except ValueError:
        loopback = False
        parsed = None
    if (len(base) > 2048 or parsed is None or parsed.scheme != "https" and not (parsed.scheme == "http" and (loopback or internal_http))
        or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment
        or ".." in unquote(parsed.path).split("/")):
        raise ValueError("Provider URL must use HTTPS, loopback HTTP, or an explicitly allowed internal HTTP host without credentials, query, or fragment.")
    return base + suffix


def bearer_token(variable: str) -> str:
    token = os.environ.get(variable, "").strip()
    if len(token) > 4096:
        raise ValueError("Provider bearer token is too long.")
    return token


def client_options(transport=None) -> dict:
    options = {"timeout": REQUEST_SECONDS, "follow_redirects": False, "trust_env": False}
    if transport is not None:
        options["transport"] = transport
    return options


def json_response(client, method: str, url: str, *, params=None, data=None, token="", deadline: float, source: str):
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        timeout = min(REQUEST_SECONDS, deadline - time.monotonic())
        if timeout <= 0:
            raise ValueError("Provider query budget expired.")
        with client.stream(method, url, params=params, data=data, headers=headers, timeout=timeout) as response:
            if response.status_code != 200:
                raise ValueError("Provider returned a non-success status.")
            body = bytearray()
            for chunk in response.iter_bytes(64 * 1024):
                if time.monotonic() > deadline:
                    raise ValueError("Provider query budget expired.")
                body.extend(chunk)
                if len(body) > MAX_RESPONSE:
                    raise ValueError("Provider response exceeded its size limit.")
        return json.loads(body)
    except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(source + " response is unavailable or invalid.") from error
