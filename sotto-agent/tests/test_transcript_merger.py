"""Tests for MergedTranscript: ordering, window filter, callback fan-out."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


import json
from pathlib import Path

from sotto.transcript import MergedTranscript, TranscriptEvent, TranscriptFileWriter


def _ev(speaker, text, seconds_ago=0):
    return TranscriptEvent(
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago),
        speaker=speaker,
        text=text,
    )


async def test_add_keeps_events_in_chronological_order():
    tx = MergedTranscript()
    # Add out of order — newer first.
    await tx.add(_ev("doctor", "newest", seconds_ago=0))
    await tx.add(_ev("patient", "oldest", seconds_ago=10))
    await tx.add(_ev("doctor", "middle", seconds_ago=5))

    events = await tx.snapshot()
    assert [e.text for e in events] == ["oldest", "middle", "newest"]


async def test_window_only_returns_recent_events():
    tx = MergedTranscript()
    await tx.add(_ev("doctor", "old", seconds_ago=120))
    await tx.add(_ev("patient", "fresh", seconds_ago=10))

    window = await tx.window(seconds=30)
    assert "fresh" in window
    assert "old" not in window


async def test_window_preserves_speaker_labels():
    tx = MergedTranscript()
    await tx.add(_ev("doctor", "How are you sleeping?", seconds_ago=5))
    await tx.add(_ev("patient", "Not great", seconds_ago=3))

    window = await tx.window(seconds=30)
    assert "doctor: How are you sleeping?" in window
    assert "patient: Not great" in window


async def test_on_new_final_fires_callback():
    tx = MergedTranscript()
    received = []

    async def cb(event):
        received.append(event)

    tx.on_new_final(cb)
    await tx.add(_ev("doctor", "trigger"))
    # Give the event loop one tick to flush the callback if it's deferred.
    await asyncio.sleep(0)
    assert len(received) == 1
    assert received[0].text == "trigger"


async def test_transcript_file_writer_appends_jsonl(tmp_path: Path):
    path = tmp_path / "transcript.jsonl"
    tx = MergedTranscript()
    tx.on_new_final(TranscriptFileWriter(path))

    await tx.add(_ev("doctor", "How are you sleeping?"))
    await tx.add(_ev("patient", "Badly"))
    await asyncio.sleep(0)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["speaker"] == "doctor"
    assert first["text"] == "How are you sleeping?"
    assert "timestamp" in first
