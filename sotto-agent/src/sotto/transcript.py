"""Merged transcript shared between the two per-track STT tasks and the cue engine."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Literal

Speaker = Literal["doctor", "patient"]


@dataclass(frozen=True)
class TranscriptEvent:
    timestamp: datetime
    speaker: Speaker
    text: str

    def render(self) -> str:
        ts = self.timestamp.strftime("%H:%M:%S")
        return f"[{ts}] {self.speaker}: {self.text}"


OnNewFinal = Callable[[TranscriptEvent], Awaitable[None]]


@dataclass
class MergedTranscript:
    _events: list[TranscriptEvent] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _callbacks: list[OnNewFinal] = field(default_factory=list)

    async def add(self, event: TranscriptEvent) -> None:
        async with self._lock:
            self._events.append(event)
            self._events.sort(key=lambda e: e.timestamp)
            callbacks = list(self._callbacks)
        for cb in callbacks:
            await cb(event)

    def on_new_final(self, callback: OnNewFinal) -> None:
        self._callbacks.append(callback)

    async def window(self, seconds: int) -> str:
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - seconds
        async with self._lock:
            recent = [e for e in self._events if e.timestamp.timestamp() >= cutoff]
        return "\n".join(e.render() for e in recent)

    async def snapshot(self) -> list[TranscriptEvent]:
        async with self._lock:
            return list(self._events)


class TranscriptFileWriter:
    """Appends each final transcript event to a jsonl file. Register via `on_new_final`."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def __call__(self, event: TranscriptEvent) -> None:
        line = json.dumps(
            {
                "timestamp": event.timestamp.isoformat(),
                "speaker": event.speaker,
                "text": event.text,
            },
            separators=(",", ":"),
        ) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
