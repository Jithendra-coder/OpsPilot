from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

RESOURCE = Resource.create({"service.name": "checkout", "service.namespace": "opspilot-demo", "deployment.environment.name": "local-lab"})
trace_provider = TracerProvider(resource=RESOURCE)
trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer("opspilot.demo.checkout")
logger_provider = LoggerProvider(resource=RESOURCE)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("checkout")

registry = CollectorRegistry()
pool_utilization = Gauge("checkout_db_pool_utilization", "Share of checkout database connections currently in use", ("service_id", "demo_run_id"), registry=registry)
requests_total = Counter("checkout_requests_total", "Checkout requests by outcome", ("status",), registry=registry)
fault_active = False
fault_run_id = "baseline"
fault_lock = threading.Lock()
pool_utilization.labels("checkout", fault_run_id).set(0.25)


def checkout():
    with fault_lock:
        failing = fault_active
    with tracer.start_as_current_span("checkout request") as request_span:
        request_span.set_attribute("http.route", "/checkout")
        if failing:
            with tracer.start_as_current_span("postgres acquire_connection") as db_span:
                db_span.set_attribute("db.system.name", "postgresql")
                db_span.set_attribute("db.operation.name", "acquire_connection")
                db_span.set_status(Status(StatusCode.ERROR, "connection acquisition timed out"))
            logger.error("Connection acquisition timed out; pool=32 in_use=32")
            requests_total.labels("error").inc()
            return 503, {"status": "degraded", "service": "checkout", "reason": "database connection acquisition timed out"}
        logger.info("Checkout request completed; database pool healthy")
        requests_total.labels("success").inc()
        return 200, {"status": "ok", "service": "checkout"}


def emit_while_failing():
    while True:
        time.sleep(5)
        with fault_lock:
            failing = fault_active
        if failing:
            checkout()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def send_json(self, status, value):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global fault_active
        if self.path == "/health":
            return self.send_json(200, {"status": "ok"})
        if self.path == "/metrics":
            body = generate_latest(registry)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/checkout":
            status, result = checkout()
            return self.send_json(status, result)
        with fault_lock:
            state = fault_active
        return self.send_json(404, {"error": "not_found", "fault_active": state})

    def do_POST(self):
        global fault_active, fault_run_id
        if self.path != "/admin/failure/on" and self.path != "/admin/failure/off":
            return self.send_json(404, {"error": "not_found"})
        with fault_lock:
            fault_active = self.path.endswith("/on")
            fault_run_id = secrets.token_hex(8) if fault_active else "baseline"
            pool_utilization.clear()
            pool_utilization.labels("checkout", fault_run_id).set(0.98 if fault_active else 0.25)
        logger.warning("Controlled local demo fault %s", "enabled" if fault_active else "cleared")
        if fault_active:
            status, result = checkout()
            return self.send_json(200, {"fault_active": True, "request_status": status, "result": result})
        return self.send_json(200, {"fault_active": False})


if __name__ == "__main__":
    threading.Thread(target=emit_while_failing, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
