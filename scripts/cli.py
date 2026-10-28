"""Interactive terminal client for a running OpsPilot API."""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import ipaddress
import json
import os
import secrets
import sys
import textwrap
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener


DEFAULT_URL = "http://127.0.0.1:8765"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new_url):
        return None


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def validate_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid OpsPilot URL and port.") from exc
    if (parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("Use an HTTP(S) origin only, such as http://127.0.0.1:8765.")
    try:
        loopback = hostname.casefold() == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = False
    if parsed.scheme != "https" and not loopback:
        raise ValueError("Passwords are only sent over HTTPS; plain HTTP is allowed for loopback hosts.")
    return value.strip().rstrip("/")


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 10):
        self.base_url = validate_base_url(base_url)
        self.timeout = timeout
        self.csrf_token = ""
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar), NoRedirectHandler())

    def request(self, method: str, path: str, payload: dict | None = None):
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.csrf_token and method in {"POST", "DELETE"} and path != "/auth/session":
            headers["X-CSRF-Token"] = self.csrf_token
        request = Request(self.base_url + "/api/v1" + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ApiError(response.status, "response_too_large", "The API response exceeded the CLI safety limit.")
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read(MAX_RESPONSE_BYTES)
            try:
                error = json.loads(raw.decode("utf-8")).get("error", {})
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                error = {}
            raise ApiError(exc.code, str(error.get("code", "request_failed")),
                str(error.get("message", "OpsPilot rejected the request."))) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):
                message = "The OpsPilot API did not respond before the timeout."
            else:
                message = "Could not reach OpsPilot. Start the API with `python app.py` and retry."
            raise ApiError(0, "connection_failed", message) from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(0, "invalid_response", "OpsPilot returned a response the CLI could not read as JSON.") from None

    def login(self, password: str, username: str | None = None):
        payload = {"password": password}
        if username:
            payload["username"] = username
        result = self.request("POST", "/auth/session", payload)
        if (result.get("authenticated") is not True or result.get("role") not in {"operator", "approver"}
                or not result.get("csrf_token")):
            raise ApiError(0, "invalid_session", "The API did not return a valid OpsPilot session.")
        self.csrf_token = result.get("csrf_token", "")
        return result

    def logout(self):
        try:
            self.request("DELETE", "/auth/session")
        finally:
            self.csrf_token = ""
            self.cookie_jar.clear()


def safe_text(value) -> str:
    text = str(value)
    return "".join(char for char in text if char in "\n\t" or unicodedata.category(char)[0] != "C")


def clip(value, width: int = 64) -> str:
    value = " ".join(safe_text(value).split()) or "-"
    return textwrap.shorten(value, width=max(4, width), placeholder="...")


def print_wrapped(label: str, value, width: int = 84):
    prefix = label
    for line in safe_text(value).splitlines() or [""]:
        print(textwrap.fill(line, width=width, initial_indent=prefix,
            subsequent_indent=" " * len(label), break_long_words=True, break_on_hyphens=False))
        prefix = " " * len(label)


def heading(title: str):
    print("\n" + "=" * 68)
    print("  " + safe_text(title))
    print("=" * 68)


def ask(prompt: str) -> str:
    return input(prompt).strip()


def confirm(prompt: str) -> bool:
    return ask(prompt + " [y/N] ").casefold() in {"y", "yes"}


def choose(items: list, label, prompt: str):
    if not items:
        print("Nothing to select.")
        return None
    for index, item in enumerate(items, 1):
        print(f"  {index:>2}. {clip(label(item), 100)}")
    while True:
        value = ask(prompt + " (number, or b to go back): ")
        if value.casefold() in {"b", "back", "q"}:
            return None
        if value.isdecimal() and 1 <= int(value) <= len(items):
            return items[int(value) - 1]
        print("Choose one of the listed numbers, or b to go back.")


def show_incidents(incidents: list):
    if not incidents:
        print("No incidents found.")
        return
    print(f"\n{'#':>2}  {'SEV':<4} {'STATUS':<19} {'SERVICE':<16} TITLE")
    print("-" * 68)
    for index, incident in enumerate(incidents, 1):
        print(f"{index:>2}  {clip(incident.get('severity'), 4):<4} "
            f"{clip(incident.get('status'), 19):<19} "
            f"{clip(incident.get('service_id'), 16):<16} {clip(incident.get('title'), 45)}")
        print(f"    {clip(incident.get('id'), 68)}")


def show_diagnosis(result: dict | None):
    if not result:
        print("No investigation result is recorded yet.")
        return
    heading("Investigation finding")
    print("Decision:    " + clip(result.get("status"), 60))
    print("Cause:       " + clip(result.get("cause_id") or "None supported", 60))
    print("Support:     " + clip(result.get("confidence", "not reported"), 60) + " (heuristic, not probability)")
    if result.get("rationale"):
        print_wrapped("Rationale:   ", result["rationale"])
    hypotheses = result.get("hypotheses") or []
    if hypotheses:
        print("\nCompeting hypotheses:")
        for item in hypotheses[:5]:
            print_wrapped("  - ", json.dumps(item, ensure_ascii=False))


def show_report(report: dict):
    incident = report.get("incident", {})
    heading("Incident report")
    print(f"{clip(incident.get('title'), 90)} [{clip(incident.get('severity'), 5)}]")
    print(f"ID: {clip(incident.get('id'), 80)}  Service: {clip(incident.get('service_id'), 50)}  State: {clip(incident.get('status'), 40)}")
    if incident.get("description"):
        print_wrapped("Description: ", incident["description"])
    investigation = report.get("investigation") or {}
    if investigation:
        show_diagnosis(investigation.get("result"))
    evidence = report.get("evidence") or []
    print(f"\nEvidence ({len(evidence)}):")
    for item in evidence[:25]:
        print(f"  - {clip(item.get('kind'), 12):<12} {clip(item.get('service_id'), 18):<18} "
            f"{clip(item.get('source'), 24)}")
        print_wrapped("      ", item.get("observation", ""))
    steps = report.get("tool_timeline") or []
    if steps:
        print(f"\nInvestigation stages ({len(steps)}):")
        for item in steps[-12:]:
            print(f"  - {clip(item.get('stage'), 34):<34} {clip(item.get('status'), 18)}")
    actions = report.get("remediation") or []
    if actions:
        print("\nRemediation history:")
        for item in actions:
            print(f"  - {clip(item.get('action_type'), 32)} | approval: {clip(item.get('approval_status'), 18)} | "
                f"verification passed: {item.get('verification_passed')}")


def show_action(item: dict):
    print("\nAction:")
    print_wrapped("  ", item.get("summary") or item.get("action_type", "Unknown action"))
    print("Type:        " + clip(item.get("action_type"), 60))
    print("Parameters:")
    for line in json.dumps(item.get("parameters", {}), ensure_ascii=False, indent=2).splitlines():
        print("  " + safe_text(line))
    if item.get("reason"):
        print_wrapped("Reason:      ", item["reason"])
    if item.get("risk"):
        print_wrapped("Risk:        ", item["risk"])
    if item.get("expected_result"):
        print_wrapped("Expected:    ", item["expected_result"])
    for key, label in (("prerequisites", "Prerequisite"), ("verification", "Verification"), ("rollback", "Rollback")):
        value = item.get(key)
        if isinstance(value, list):
            for detail in value:
                print_wrapped(f"{label}: ", detail)
        elif value:
            print_wrapped(f"{label}: ", value)
    print("Incident:    " + clip(item.get("incident_title"), 90))
    print("Status:      " + clip(item.get("approval_status"), 40))
    if item.get("expires_at"):
        print("Expires:     " + clip(item["expires_at"], 60))


def list_incidents(client: ApiClient):
    result = client.request("GET", "/incidents?limit=25")
    incidents = result.get("incidents", [])
    show_incidents(incidents)
    selected = choose(incidents, lambda item: f"{item.get('id')} | {item.get('title')}", "Open incident")
    return selected


def investigate(client: ApiClient, incident_id: str):
    if not confirm("Run a read-only investigation on this incident?"):
        return
    key = "cli-" + secrets.token_urlsafe(18)
    result = client.request("POST", f"/incidents/{incident_id}/investigate", {"idempotency_key": key})
    show_diagnosis((result.get("investigation") or {}).get("result"))
    print("Idempotency key: " + key)


def propose_action(client: ApiClient, incident_id: str):
    print("This creates an approval request; it does not execute an action. Actions are simulator-only.")
    if not confirm("Create the allowlisted proposal?"):
        return
    result = client.request("POST", f"/incidents/{incident_id}/remediation/propose", {})
    proposal = result.get("proposal", {})
    show_action({**proposal, "approval_status": (proposal.get("approval") or {}).get("status")})
    print("Approval ID: " + clip((proposal.get("approval") or {}).get("id"), 70))


def add_comment(client: ApiClient, incident_id: str):
    body = ask("Audited incident note: ")
    if not body:
        print("No note added.")
        return
    client.request("POST", f"/incidents/{incident_id}/comments", {"body": body})
    print("Audited note added.")


def incident_workspace(client: ApiClient, incident: dict, role: str):
    incident_id = incident["id"]
    while True:
        try:
            incident = client.request("GET", f"/incidents/{incident_id}").get("incident", incident)
        except ApiError as exc:
            print(f"OpsPilot error ({exc.status} {safe_text(exc.code)}): {safe_text(exc.message)}")
            return
        heading(f"{incident.get('title', 'Incident')} | {incident_id}")
        print(f"State: {incident.get('status')}  Severity: {incident.get('severity')}  Service: {incident.get('service_id')}")
        print("  1. View incident report")
        if role == "operator":
            print("  2. Investigate (read-only)")
            print("  3. Propose an allowlisted simulator action")
        print("  4. Add an audited note")
        print("  0. Back")
        choice = ask("Select: ")
        if choice == "0":
            return
        try:
            if choice == "1":
                show_report(client.request("GET", f"/incidents/{incident_id}/report").get("report", {}))
            elif choice == "2" and role == "operator":
                investigate(client, incident_id)
            elif choice == "3" and role == "operator":
                propose_action(client, incident_id)
            elif choice == "4":
                add_comment(client, incident_id)
            else:
                print("Choose one of the listed actions.")
        except ApiError as exc:
            print(f"OpsPilot error ({exc.status} {safe_text(exc.code)}): {safe_text(exc.message)}")


def start_replay(client: ApiClient):
    scenarios = client.request("GET", "/scenarios").get("scenarios", [])
    selected = choose(scenarios, lambda item: f"{item.get('id')} | {item.get('severity')} | {item.get('service_id')} | {item.get('title')}", "Choose replay")
    if not selected:
        return None
    print_wrapped("Description: ", selected.get("description", ""))
    if not confirm("Start this isolated replay? It changes simulator state only."):
        return None
    result = client.request("POST", "/simulations/start", {"scenario_id": selected["id"]})
    incident = result.get("incident", {})
    print(f"Replay started: {clip(incident.get('id'), 70)} | {clip(incident.get('title'), 90)}")
    return incident


def create_incident(client: ApiClient):
    services = client.request("GET", "/services").get("services", [])
    service = choose(services, lambda item: f"{item.get('id')} | {item.get('name')}", "Choose affected service")
    if not service:
        return None
    heading("Create incident")
    title = ask("Title: ")
    description = ask("Description: ")
    severities = ["P1", "P2", "P3", "P4"]
    severity = choose(severities, lambda item: item, "Severity")
    if not title or not description or not severity:
        print("Incident creation cancelled; title, description, and severity are required.")
        return None
    if not confirm(f"Create {severity} incident for {service.get('id')}?"):
        return None
    result = client.request("POST", "/incidents", {"title": title, "description": description,
        "severity": severity, "service_id": service["id"]})
    incident = result.get("incident", {})
    print(f"Incident created: {clip(incident.get('id'), 70)}")
    return incident


def approval_queue(client: ApiClient, role: str):
    status = "pending" if role == "approver" else "approved"
    items = client.request("GET", "/approvals?" + urlencode({"status": status})).get("approvals", [])
    selected = choose(items, lambda item: f"{item.get('approval_status')} | {item.get('incident_title')} | {item.get('summary') or item.get('action_type')}",
        "Review approval" if role == "approver" else "Choose approved action")
    if not selected:
        return
    show_action(selected)
    if role == "approver":
        decision = ask("Decision: [a]pprove, [r]eject, [b]ack: ").casefold()
        if decision not in {"a", "r"}:
            return
        note = ask("Decision note (at least 6 characters): ")
        if len(note) < 6:
            print("Decision note must be at least 6 characters; no decision was sent.")
            return
        verb = "approve" if decision == "a" else "reject"
        if not confirm(f"{verb.title()} this exact proposal?"):
            return
        result = client.request("POST", f"/approvals/{selected['approval_id']}/{verb}", {"note": note})
        print("Approval status: " + clip((result.get("approval") or {}).get("status"), 40))
        return
    if not confirm("Execute this approved action against the isolated simulator?"):
        return
    key = "cli-" + secrets.token_urlsafe(18)
    result = client.request("POST", f"/actions/{selected['proposal_id']}/execute", {"idempotency_key": key})
    execution = result.get("execution", {})
    verification = result.get("verification", {})
    print("Execution: " + clip(execution.get("status"), 40))
    print("Verification passed: " + str(verification.get("passed")))


def run_evaluation(client: ApiClient):
    print("This checks seeded signature consistency; it is not independent field accuracy.")
    if not confirm("Run the seeded evaluation suite?"):
        return
    result = client.request("POST", "/evaluations")
    evaluation = result.get("evaluation", {})
    print(f"Cases: {evaluation.get('case_count', 'n/a')}  "
        f"Seeded match rate: {evaluation.get('accuracy', 'n/a')}  "
        f"Inconclusive: {evaluation.get('inconclusive', 'n/a')}")
    print("Scope: fixture-rule consistency only; not field diagnosis accuracy.")


def home(client: ApiClient, role: str):
    while True:
        heading(f"OpsPilot CLI | {role.title()} | {client.base_url}")
        print("  1. Overview")
        print("  2. List and open incidents")
        if role == "operator":
            print("  3. Start an isolated replay")
            print("  4. Create a manual incident")
            print("  5. Execute an approved simulator action")
            print("  6. Run seeded evaluation")
        else:
            print("  3. Review pending approvals")
        print("  0. Sign out and exit")
        choice = ask("Select: ")
        try:
            if choice == "0":
                return
            if choice == "1":
                data = client.request("GET", "/overview")
                stats = data.get("stats", {})
                print("\nServices: {} ({} healthy) | Open incidents: {} | Investigations: {}".format(
                    stats.get("services", 0), stats.get("healthy_services", 0),
                    stats.get("open_incidents", 0), stats.get("investigations", 0)))
                show_incidents(data.get("incidents", [])[:10])
            elif choice == "2":
                incident = list_incidents(client)
                if incident:
                    incident_workspace(client, incident, role)
            elif choice == "3" and role == "operator":
                incident = start_replay(client)
                if incident:
                    incident_workspace(client, incident, role)
            elif choice == "3" and role == "approver":
                approval_queue(client, role)
            elif choice == "4" and role == "operator":
                incident = create_incident(client)
                if incident:
                    incident_workspace(client, incident, role)
            elif choice == "5" and role == "operator":
                approval_queue(client, role)
            elif choice == "6" and role == "operator":
                run_evaluation(client)
            else:
                print("Choose one of the listed actions.")
        except ApiError as exc:
            print(f"OpsPilot error ({exc.status} {safe_text(exc.code)}): {safe_text(exc.message)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("OPSPILOT_URL", DEFAULT_URL),
        help="OpsPilot API origin (default: %(default)s; remote URLs must use HTTPS)")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        print("OpsPilot CLI needs an interactive terminal.", file=sys.stderr)
        return 2
    try:
        client = ApiClient(args.url)
        health = client.request("GET", "/health")
        if health.get("status") != "ok":
            raise ApiError(503, "not_ready", "OpsPilot is not ready yet.")
    except (ValueError, ApiError) as exc:
        print(safe_text(str(exc)), file=sys.stderr)
        return 1
    heading("OpsPilot | Incident command line")
    print(f"Connected to {client.base_url} ({clip(health.get('mode', 'API ready'), 50)}).")
    print("Team accounts use a username; leave it blank for the local role-password demo.")
    for attempt in range(3):
        try:
            username = input("Username (optional): ").strip()
            password = getpass.getpass("Password: ")
            session = client.login(password, username or None)
            break
        except ApiError as exc:
            print(f"Sign-in failed ({exc.status}): {safe_text(exc.message)}")
            if exc.status != 401 or attempt == 2:
                return 1
    try:
        home(client, session["role"])
    except (KeyboardInterrupt, EOFError):
        print("\nSigning out...")
    finally:
        try:
            client.logout()
        except ApiError:
            print("Session could not be revoked over the API; it will expire automatically.")
    print("Signed out.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nExited.")
