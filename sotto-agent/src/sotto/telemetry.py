"""Opt-in OpenTelemetry export for the Sotto agent.

If the environment is configured for an OTLP-compatible backend, this wires
``livekit.agents.telemetry.set_tracer_provider`` so the spans LiveKit already emits flow
to that backend. If no telemetry env vars are present, it returns ``False`` and the agent
runs exactly like today (purely local jsonl + data-channel observability).

Supported configurations (checked in order):

1. **LangFuse** — set ``LANGFUSE_HOST``, ``LANGFUSE_PUBLIC_KEY``, ``LANGFUSE_SECRET_KEY``.
2. **Generic OTLP/HTTP** — set ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and optionally
   ``OTEL_EXPORTER_OTLP_HEADERS``). This is the standard OpenTelemetry contract honored
   by Honeycomb, Datadog, Jaeger, Tempo, and anything else that speaks OTLP/HTTP.

Both paths use a ``BatchSpanProcessor`` so exports are non-blocking.
"""

from __future__ import annotations

import base64
import logging
import os

logger = logging.getLogger(__name__)


def _have_langfuse_config() -> bool:
    return all(
        os.getenv(k) for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    )


def _have_generic_otlp_config() -> bool:
    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def setup_tracing() -> bool:
    """Activate OTel export if env vars are present. Returns True iff tracing was wired.

    Safe to call unconditionally — if no relevant env vars are set, this is a no-op.
    Import errors (missing OTel deps) are logged and swallowed so the agent never fails
    to boot because telemetry wasn't installed.
    """
    if not (_have_langfuse_config() or _have_generic_otlp_config()):
        return False

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from livekit.agents.telemetry import set_tracer_provider
    except ImportError:
        logger.warning(
            "telemetry env vars present but OpenTelemetry deps not installed; "
            "install with `uv add opentelemetry-sdk opentelemetry-exporter-otlp-proto-http`. "
            "Continuing without tracing.",
        )
        return False

    # LangFuse path takes precedence — it derives the OTLP endpoint from LANGFUSE_HOST and
    # builds the Basic auth header from the public/secret key pair.
    if _have_langfuse_config():
        public_key = os.environ["LANGFUSE_PUBLIC_KEY"]
        secret_key = os.environ["LANGFUSE_SECRET_KEY"]
        host = os.environ["LANGFUSE_HOST"].rstrip("/")
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", f"{host}/api/public/otel")
        os.environ.setdefault("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=Basic {auth}")
        backend = f"LangFuse ({host})"
    else:
        backend = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing enabled — backend=%s", backend)
    return True


__all__ = ["setup_tracing"]
