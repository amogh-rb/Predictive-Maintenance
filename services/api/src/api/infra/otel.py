"""OpenTelemetry wiring for the API (PLAN §2 Observability: "OpenTelemetry ->
OTel Collector -> Prometheus + Grafana"; session 8). Exports request traces
and RED metrics (rate/errors/duration) over OTLP to the `otel-collector`
service (profile `obs`), which re-exposes them for Prometheus to scrape —
see `infra/compose/otel-collector-config.yaml`. A no-op if
`OTEL_EXPORTER_OTLP_ENDPOINT` is unset, so running the `core` profile alone
(without `obs`) doesn't block on a collector that isn't there.
"""
from __future__ import annotations

import os

from fastapi import FastAPI


def instrument(app: FastAPI) -> None:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": "fleetpulse-api"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint, insecure=True))
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    FastAPIInstrumentor.instrument_app(app)
