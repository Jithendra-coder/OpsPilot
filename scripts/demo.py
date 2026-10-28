"""Start and control OpsPilot's isolated live-telemetry demo using Docker or Podman Compose."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local-demo"
ENV_FILE = STATE / "demo.env"
TOKEN_FILE = STATE / "alertmanager-token"
COMPOSE = ROOT / "demo" / "compose.yaml"


def runtime() -> str:
    requested = os.environ.get("CONTAINER_RUNTIME")
    for candidate in ([requested] if requested else ["podman", "docker"]):
        if candidate and shutil.which(candidate):
            return candidate
    raise SystemExit("Install Docker Compose or Podman Compose, then retry.")


def ensure_local_credentials() -> None:
    STATE.mkdir(exist_ok=True)
    if not ENV_FILE.exists():
        values = {
            "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "OPSPILOT_OPERATOR_USERNAME": "operator",
            "OPSPILOT_OPERATOR_PASSWORD": secrets.token_urlsafe(32),
            "OPSPILOT_APPROVER_USERNAME": "reviewer",
            "OPSPILOT_APPROVER_PASSWORD": secrets.token_urlsafe(32),
            "OPSPILOT_ALERT_WEBHOOK_TOKEN": secrets.token_urlsafe(48),
        }
        ENV_FILE.write_text("".join(f"{name}={value}\n" for name, value in values.items()), encoding="utf-8")
        if os.name != "nt":
            ENV_FILE.chmod(0o600)
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    token = values.get("OPSPILOT_ALERT_WEBHOOK_TOKEN", "")
    if len(token) < 32 or any(char.isspace() for char in token):
        raise SystemExit("The local Alertmanager token in .local-demo/demo.env must be 32+ non-whitespace characters.")
    if not TOKEN_FILE.exists() or TOKEN_FILE.read_text(encoding="utf-8") != token:
        TOKEN_FILE.write_text(token, encoding="utf-8")
        if os.name != "nt":
            TOKEN_FILE.chmod(0o600)


def compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([runtime(), "compose", "-f", str(COMPOSE), "--env-file", str(ENV_FILE), *arguments], cwd=ROOT, check=check)


def set_fault(enabled: bool) -> None:
    url = "http://127.0.0.1:8081/admin/failure/" + ("on" if enabled else "off")
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError) as error:
        raise SystemExit("The checkout demo is not ready; run `python -m scripts.demo up` first.") from error


def wait_for_app() -> None:
    context = ssl._create_unverified_context()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    deadline = time.monotonic() + 90
    last_health = None
    last_error = None
    while time.monotonic() < deadline:
        try:
            with opener.open("https://localhost:8765/api/v1/health", timeout=3) as response:
                health = json.loads(response.read())
            last_health = health
            if health.get("status") == "ok" and health.get("database") == "ready":
                return
        except (OSError, urllib.error.URLError, ValueError) as error:
            last_error = type(error).__name__ + ": " + str(error)
        time.sleep(1)
    raise SystemExit("OpsPilot did not become ready; last health response: " + json.dumps(last_health, sort_keys=True) + "; last probe error: " + str(last_error))


def verify_live_path() -> None:
    values = dict(line.split("=", 1) for line in ENV_FILE.read_text(encoding="utf-8").splitlines() if "=" in line)
    headers = {"Origin": "https://localhost:8765"}
    set_fault(False)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:9093/api/v2/alerts", timeout=5) as response:
                alerts = json.loads(response.read())
            if not any(item.get("status", {}).get("state") == "active" and item.get("labels", {}).get("service_id") == "checkout" for item in alerts):
                break
        except (OSError, urllib.error.URLError, ValueError):
            pass
        time.sleep(2)
    else:
        raise SystemExit("The previous checkout alert did not clear; inspect Prometheus and Alertmanager before retrying.")
    with httpx.Client(base_url="https://localhost:8765", verify=False, timeout=10) as client:
        login = client.post("/api/v1/auth/session", json={
            "username": values["OPSPILOT_OPERATOR_USERNAME"],
            "password": values["OPSPILOT_OPERATOR_PASSWORD"],
        })
        if login.status_code != 200:
            raise SystemExit("The configured demo operator could not sign in: " + login.text)
        csrf = login.json()["csrf_token"]
        headers["X-CSRF-Token"] = csrf
        before = {item["id"] for item in client.get("/api/v1/incidents", params={"limit": 100}).json()["incidents"]}
        set_fault(True)
        try:
            incident = None
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                listing = client.get("/api/v1/incidents", params={"limit": 100})
                listing.raise_for_status()
                incident = next((item for item in listing.json()["incidents"]
                    if item["id"] not in before and item["source"] == "alertmanager_webhook"
                    and item["service_id"] == "checkout" and item["created_at"]), None)
                if incident:
                    break
                time.sleep(2)
            if not incident:
                raise SystemExit("Prometheus did not deliver the checkout alert to OpsPilot within 75 seconds.")
            time.sleep(15)  # Let Tempo complete its short demo-only live-store block before the investigation.
            result = client.post(f"/api/v1/incidents/{incident['id']}/investigate", json={
                "idempotency_key": "compose-demo-live-path-verify-001",
            }, headers=headers, timeout=120)
            result.raise_for_status()
            report = client.get(f"/api/v1/incidents/{incident['id']}/report")
            report.raise_for_status()
            evidence = report.json()["report"]["evidence"]
            sources = {item.get("provenance") for item in evidence}
            required = {"prometheus-http-api", "loki-http-api", "tempo-search-api"}
            if not required.issubset(sources):
                raise SystemExit("The live investigation did not include all provider evidence: " + ", ".join(sorted(required - sources)))
            diagnosis = result.json()["investigation"]["result"]
            if diagnosis.get("status") != "supported" or diagnosis.get("cause_id") != "db_pool":
                raise SystemExit("The live evidence did not support the expected database-pool diagnosis: " + json.dumps(diagnosis))
            proposal = client.post(f"/api/v1/incidents/{incident['id']}/remediation/propose", json={}, headers=headers)
            if proposal.status_code != 409 or proposal.json().get("error", {}).get("code") != "sandbox_only":
                raise SystemExit("A provider-backed incident crossed the simulator-only action boundary.")
            print("PASS: Alertmanager created " + incident["id"] + "; Prometheus, Loki, and Tempo evidence supported db_pool; external remediation was denied.")
        finally:
            set_fault(False)


def trust_instructions() -> None:
    try:
        context = ssl._create_unverified_context()
        urllib.request.urlopen("https://localhost:8765/", context=context, timeout=5).close()
    except (OSError, urllib.error.URLError):
        raise SystemExit("Start the demo and visit https://localhost:8765 once, then retry trust.") from None
    certificate = STATE / "caddy-root.crt"
    subprocess.run([runtime(), "compose", "-f", str(COMPOSE), "--env-file", str(ENV_FILE),
        "cp", "caddy:/data/caddy/pki/authorities/local/root.crt", str(certificate)], cwd=ROOT, check=True)
    print("Local Caddy root certificate copied to " + str(certificate))
    if sys.platform == "win32":
        print("Review the certificate, then trust it for this Windows user with:")
        print("Import-Certificate -FilePath .local-demo/caddy-root.crt -CertStoreLocation Cert:\\CurrentUser\\Root")
    elif sys.platform == "darwin":
        print("Review the certificate, then trust it with: security add-trusted-cert -d -r trustRoot -k ~/Library/Keychains/login.keychain-db .local-demo/caddy-root.crt")
    else:
        print("Review the certificate, then install it in your local trust store using your distribution's CA tool.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "fault", "recover", "verify", "trust", "status", "down"))
    args = parser.parse_args(argv)
    if args.command == "up":
        ensure_local_credentials()
        compose("down")
        compose("up", "--build", "--detach")
        wait_for_app()
        print("OpsPilot: https://localhost:8765")
        print("Generated local sign-in credentials: " + str(ENV_FILE))
        print("Control the live checkout failure with `python -m scripts.demo fault` and `python -m scripts.demo recover`.")
    elif args.command in {"fault", "recover"}:
        set_fault(args.command == "fault")
        if args.command == "fault":
            print("Prometheus will alert after its configured 10-second hold; allow a few more seconds for webhook delivery.")
    elif args.command == "trust":
        ensure_local_credentials()
        trust_instructions()
    elif args.command == "verify":
        ensure_local_credentials()
        wait_for_app()
        verify_live_path()
    elif args.command == "status":
        ensure_local_credentials()
        compose("ps")
    else:
        ensure_local_credentials()
        compose("down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
