"""Tests for the opt-in OpenTelemetry setup."""

from __future__ import annotations

import pytest

from sotto.telemetry import setup_tracing


@pytest.fixture(autouse=True)
def _clear_telemetry_env(monkeypatch: pytest.MonkeyPatch):
    for k in (
        "LANGFUSE_HOST",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
    ):
        monkeypatch.delenv(k, raising=False)


def test_setup_tracing_is_noop_when_env_unset():
    # No env vars → no tracing wired, no exception.
    assert setup_tracing() is False


def test_setup_tracing_is_noop_with_partial_langfuse_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    # Missing PUBLIC + SECRET keys → still considered unset, no tracing wired.
    assert setup_tracing() is False
