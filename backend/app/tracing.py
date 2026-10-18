"""Cloud Trace via OpenTelemetry: request spans here, agent / LLM / tool spans come from ADK's instrumentation.

Enabled by ENABLE_TRACE (default true when the exporter package is installed). Export is batched in a
background thread, so it adds no request latency. The runtime service account needs roles/cloudtrace.agent.
"""
from __future__ import annotations

import contextlib
import os

from . import config
from .db import log

ENABLED = False
_tracer = None


def setup() -> None:
    global ENABLED, _tracer
    if os.getenv("ENABLE_TRACE", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({
            "service.name": os.getenv("K_SERVICE", "retailnova-api"),
            "service.version": config.VERSION,
        }))
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=config.PROJECT)))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("retailnova")
        ENABLED = True
        log("INFO", "cloud trace enabled")
    except Exception as e:
        log("WARNING", "cloud trace disabled", error=type(e).__name__, detail=str(e)[:160])


def span(name: str, **attrs):
    """Context manager for a span; a no-op when tracing is off."""
    if not ENABLED or _tracer is None:
        return contextlib.nullcontext()
    return _tracer.start_as_current_span(name, attributes={k: v for k, v in attrs.items() if v is not None})
