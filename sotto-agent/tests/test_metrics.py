"""Tests for the observability metrics module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sotto.metrics import (
    DataChannelMetricsSink,
    EvalEvent,
    JsonlMetricsEventSink,
    JsonlMetricsSessionSink,
    LLMEvent,
    MetricsCollector,
    STTEvent,
)


class _FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


async def test_collector_aggregates_stt_and_emits_events(tmp_path: Path):
    clock = _FakeClock()
    events_path = tmp_path / "events.jsonl"
    sessions_path = tmp_path / "sessions.jsonl"
    collector = MetricsCollector(
        sinks=[JsonlMetricsEventSink(events_path), JsonlMetricsSessionSink(sessions_path)],
        live_publish_interval_s=0.0,
        clock=clock,
    )
    collector.start_session(session_id="sess-1", room_name="room-a", job_id="job-x")

    await collector.record_stt(STTEvent(speaker="doctor", latency_ms=200, audio_duration_s=1.5))
    clock.advance(0.5)
    await collector.record_stt(STTEvent(speaker="patient", latency_ms=400, audio_duration_s=2.0))

    snap = collector.snapshot()
    assert snap["transcripts"]["total"] == 2
    assert snap["transcripts"]["by_speaker"] == {"doctor": 1, "patient": 1}
    assert snap["stt"]["count"] == 2
    assert snap["stt"]["audio_duration_s"] == pytest.approx(3.5)
    assert snap["stt"]["p50_ms"] in (200.0, 400.0)

    lines = events_path.read_text().splitlines()
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["kind"] == "stt"
    assert parsed["speaker"] == "doctor"
    assert parsed["latency_ms"] == 200.0


async def test_collector_records_llm_with_errors_and_tokens(tmp_path: Path):
    collector = MetricsCollector(
        sinks=[JsonlMetricsEventSink(tmp_path / "events.jsonl")],
        live_publish_interval_s=0.0,
    )
    collector.start_session(session_id="s")

    await collector.record_llm(
        LLMEvent(
            ttft_ms=300,
            duration_ms=900,
            prompt_tokens=120,
            completion_tokens=60,
            total_tokens=180,
            cached_tokens=10,
            tokens_per_second=66.6,
        )
    )
    await collector.record_llm(
        LLMEvent(
            ttft_ms=None,
            duration_ms=0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cached_tokens=None,
            tokens_per_second=None,
            error=True,
        )
    )

    snap = collector.snapshot()
    assert snap["llm"]["calls"] == 1
    assert snap["llm"]["errors"] == 1
    assert snap["llm"]["tokens"]["total"] == 180
    assert snap["llm"]["tokens"]["cached"] == 10
    assert snap["llm"]["ttft"]["count"] == 1


async def test_collector_eval_action_histogram_and_dedup(tmp_path: Path):
    collector = MetricsCollector(live_publish_interval_s=0.0)
    collector.start_session(session_id="s")

    await collector.record_eval(EvalEvent(action="card", evaluate_ms=120))
    await collector.record_eval(EvalEvent(action="none", evaluate_ms=80))
    await collector.record_eval(EvalEvent(action="none", evaluate_ms=80, dedup_dropped=True))

    snap = collector.snapshot()
    assert snap["cue_engine"]["actions"] == {"card": 1, "none": 2}
    assert snap["cue_engine"]["dedup_dropped"] == 1
    assert snap["cue_engine"]["count"] == 3


async def test_collector_record_card_emitted_counts_by_type():
    collector = MetricsCollector(live_publish_interval_s=0.0)
    collector.start_session(session_id="s")

    await collector.record_card_emitted("suggested_question")
    await collector.record_card_emitted("suggested_question")
    await collector.record_card_emitted("protocol_direction")

    snap = collector.snapshot()
    assert snap["cards"]["total"] == 3
    assert snap["cards"]["by_type"] == {
        "suggested_question": 2,
        "protocol_direction": 1,
    }


async def test_end_session_writes_summary(tmp_path: Path):
    sessions_path = tmp_path / "sessions.jsonl"
    collector = MetricsCollector(
        sinks=[JsonlMetricsSessionSink(sessions_path)], live_publish_interval_s=0.0
    )
    collector.start_session(session_id="sess-end", room_name="room-end", job_id="job-end")
    collector.record_participant_join("doctor-abc", role="doctor")
    await collector.record_stt(STTEvent(speaker="doctor", latency_ms=150))

    summary = await collector.end_session(disconnect_reason="CLIENT_INITIATED")
    assert summary["final"] is True
    assert summary["disconnect_reason"] == "CLIENT_INITIATED"
    assert summary["session_id"] == "sess-end"
    assert summary["participants"][0]["identity"] == "doctor-abc"

    line = sessions_path.read_text().strip()
    parsed = json.loads(line)
    assert parsed["session_id"] == "sess-end"
    assert parsed["transcripts"]["total"] == 1


async def test_data_channel_sink_publishes_envelope():
    captured = {}

    class FakeLocal:
        async def publish_data(self, payload, *, reliable, topic):
            captured["payload"] = payload
            captured["reliable"] = reliable
            captured["topic"] = topic

    class FakeRoom:
        local_participant = FakeLocal()

    sink = DataChannelMetricsSink(FakeRoom())
    await sink.emit_snapshot({"hello": "world"})

    assert captured["topic"] == "sotto_metrics"
    assert captured["reliable"] is False
    body = json.loads(captured["payload"].decode("utf-8"))
    assert body["type"] == "sotto_metrics"
    assert body["data"] == {"hello": "world"}


async def test_data_channel_sink_swallows_publish_errors():
    class BrokenLocal:
        async def publish_data(self, *_args, **_kwargs):
            raise RuntimeError("network gone")

    class BrokenRoom:
        local_participant = BrokenLocal()

    sink = DataChannelMetricsSink(BrokenRoom())
    # Must not raise — observability is best-effort.
    await sink.emit_snapshot({"a": 1})


async def test_live_publish_is_throttled():
    snapshots: list[dict] = []

    class CapturingSink:
        async def emit_event(self, event):
            return None

        async def emit_snapshot(self, snapshot):
            snapshots.append(snapshot)

        async def emit_session(self, summary):
            return None

    clock = _FakeClock()
    collector = MetricsCollector(
        sinks=[CapturingSink()], live_publish_interval_s=1.0, clock=clock
    )
    collector.start_session(session_id="s")

    await collector.record_stt(STTEvent(speaker="doctor", latency_ms=100))
    # 0.5s later — below interval, should NOT publish.
    clock.advance(0.5)
    await collector.record_stt(STTEvent(speaker="doctor", latency_ms=100))
    # 0.6s more (1.1s total since first publish) — should publish again.
    clock.advance(0.6)
    await collector.record_stt(STTEvent(speaker="doctor", latency_ms=100))

    assert len(snapshots) == 2
