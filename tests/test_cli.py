import json
import io
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer

from scripts.cli import ApiClient, safe_text, show_action, validate_base_url


class CliApiHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, status, body, headers=None):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        self.send_json(200, {"status": "ok", "mode": "controlled_local_lab"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v1/auth/session" and body.get("password") == "correct-password":
            self.send_json(200, {"authenticated": True, "csrf_token": "csrf-value", "role": "operator"},
                {"Set-Cookie": "opspilot_session=session-value; Path=/; HttpOnly; SameSite=Strict"})
            return
        if (self.path == "/api/v1/probe" and self.headers.get("Cookie", "").find("opspilot_session=session-value") >= 0
                and self.headers.get("X-CSRF-Token") == "csrf-value"):
            self.send_json(200, {"accepted": True, "payload": body})
            return
        self.send_json(403, {"error": {"code": "csrf_rejected", "message": "Request verification failed."}})


class InteractiveCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), CliApiHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:{}".format(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_login_cookie_and_csrf_are_reused_for_mutation(self):
        client = ApiClient(self.url)
        session = client.login("correct-password")
        self.assertEqual(session["role"], "operator")
        self.assertEqual(client.request("POST", "/probe", {"ok": True}), {"accepted": True, "payload": {"ok": True}})

    def test_remote_http_and_credentials_in_url_are_rejected(self):
        for value in ("http://example.com", "https://user:secret@example.com", "http://127.0.0.1:8000/path"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_base_url(value)

    def test_terminal_output_removes_escape_controls(self):
        self.assertEqual(safe_text("alert\x1b[31mred\x1b[0m"), "alert[31mred[0m")

    def test_action_parameters_are_printed_without_truncation(self):
        value = "parameter-" + ("x" * 160)
        output = io.StringIO()
        with redirect_stdout(output):
            show_action({"action_type": "restore", "parameters": {"token": value}})
        self.assertIn(value, output.getvalue().replace("\n", ""))


if __name__ == "__main__":
    unittest.main()
