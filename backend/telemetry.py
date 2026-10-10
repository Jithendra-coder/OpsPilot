"""Low-cardinality API metrics and opt-in OpenTelemetry OTLP export."""

from __future__ import annotations

import os

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

registry = CollectorRegistry()
http_requests = Counter("opspilot_http_requests_total", "HTTP requests handled by OpsPilot", ("method", "route", "status"), registry=registry)
http_duration = Histogram("opspilot_http_request_duration_seconds", "HTTP request duration", ("method", "route"), registry=registry)

try:
    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": "opspilot-api", "service.version": "1.0.0"})
    trace_provider = TracerProvider(resource=resource)
    meter_readers = []
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        meter_readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
    trace.set_tracer_provider(trace_provider)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=meter_readers))
    tracer = trace.get_tracer("opspilot.api")
    meter = metrics.get_meter("opspilot.api")
    otel_requests = meter.create_counter("http.server.request.count")
    otel_duration = meter.create_histogram("http.server.request.duration", unit="s")
except ImportError:
    tracer = None
    otel_requests = otel_duration = None


def record_request(method: str, route: str, status: int, elapsed: float):
    http_requests.labels(method, route, str(status)).inc()
    http_duration.labels(method, route).observe(elapsed)
    if otel_requests:
        attributes = {"http.request.method": method, "http.route": route, "http.response.status_code": status}
        otel_requests.add(1, attributes)
        otel_duration.record(elapsed, attributes)


def metrics_text() -> bytes:
    return generate_latest(registry)
