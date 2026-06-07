"""Tests for the three sinks."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from sotto.sinks import Card, DataChannelSink, JsonlSink, StdoutSink


def _card() -> Card:
    return Card(
        type="suggested_question",
        content="Ask about caffeine intake.",
        rationale="Patient described tremors, caffeine is a common cause.",
        triggered_by_speaker="patient",
        transcript_snippet="my hands have been shaking",
    )


def test_card_serializes_with_all_fields():
    card = _card()
    payload = card.to_dict()
    expected_keys = {
        "id",
        "type",
        "content",
        "rationale",
        "triggered_by_speaker",
        "transcript_snippet",
        "source",
        "kb_id",
        "triggered_at",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["type"] == "suggested_question"
    assert payload["source"] == "adaptive"
    assert payload["kb_id"] is None


async def test_stdout_sink_writes_card_content():
    import io

    buf = io.StringIO()
    sink = StdoutSink(console=Console(file=buf, width=120, record=True))
    await sink.emit(_card())
    out = buf.getvalue()
    assert "Ask about caffeine intake." in out
    assert "Suggested Next Question" in out
    assert "patient" in out


async def test_jsonl_sink_appends_one_line_per_emit(tmp_path: Path):
    path = tmp_path / "cues.jsonl"
    sink = JsonlSink(path)
    await sink.emit(_card())
    await sink.emit(_card())

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["content"] == "Ask about caffeine intake."
    assert parsed["type"] == "suggested_question"


async def test_data_channel_sink_publishes_json_on_correct_topic():
    captured = {}

    class FakeLocal:
        async def publish_data(self, payload, *, reliable, topic):
            captured["payload"] = payload
            captured["reliable"] = reliable
            captured["topic"] = topic

    class FakeRoom:
        local_participant = FakeLocal()

    sink = DataChannelSink(FakeRoom())
    await sink.emit(_card())

    assert captured["topic"] == "sotto_cue"
    assert captured["reliable"] is True
    body = json.loads(captured["payload"].decode("utf-8"))
    assert body["type"] == "sotto_cue"
    assert body["data"]["content"] == "Ask about caffeine intake."
    assert body["data"]["type"] == "suggested_question"


async def test_data_channel_sink_swallows_publish_errors():
    class BrokenLocal:
        async def publish_data(self, *_args, **_kwargs):
            raise RuntimeError("network gone")

    class BrokenRoom:
        local_participant = BrokenLocal()

    sink = DataChannelSink(BrokenRoom())
    # Must not raise — sinks are best-effort.
    await sink.emit(_card())
