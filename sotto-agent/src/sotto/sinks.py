"""Cue card data type and the three sinks (stdout, data channel, jsonl)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)

CardType = Literal["suggested_question", "patient_context", "protocol_direction"]
CardSource = Literal["kb", "adaptive"]


@dataclass
class Card:
    type: CardType
    content: str
    rationale: str
    triggered_by_speaker: str
    transcript_snippet: str
    source: CardSource = "adaptive"
    kb_id: str | None = None
    # Model's own 0-1 estimate of how useful surfacing this card is RIGHT NOW. The engine gates
    # on it (emit only above a threshold) in place of a fixed time-based cooldown.
    usefulness: float = 1.0
    # Optional presentation overrides used ONLY by the flag-gated demo script (never the LLM
    # cue engine). ``header`` replaces the card's default section label; ``rows`` renders a
    # multi-line patient_context card (each row: heading/detail/source/tone) as in the UI mockup.
    header: str | None = None
    rows: list[dict] | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    triggered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class CueSink(Protocol):
    async def emit(self, card: Card) -> None: ...


_TYPE_STYLE = {
    "suggested_question": ("cyan", "Suggested Next Question"),
    "patient_context": ("green", "Patient Context"),
    "protocol_direction": ("magenta", "Protocol Direction"),
}


class StdoutSink:
    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def emit(self, card: Card) -> None:
        color, label = _TYPE_STYLE.get(card.type, ("white", card.type))
        body = Text()
        body.append(card.content + "\n\n", style="bold")
        body.append("Why: ", style="dim")
        body.append(card.rationale + "\n", style="italic")
        body.append("Trigger: ", style="dim")
        body.append(f"{card.triggered_by_speaker} — “{card.transcript_snippet}”", style="dim")
        self._console.print(
            Panel(body, title=f"[{color}]● {label}[/{color}]", border_style=color, expand=False)
        )


class DataChannelSink:
    """Publish the card as JSON on the `sotto_cue` data topic of the agent's room."""

    TOPIC = "sotto_cue"

    def __init__(self, room) -> None:  # rtc.Room — kept untyped to avoid import at module load
        self._room = room

    async def emit(self, card: Card) -> None:
        # Wrap in a {type, data} envelope so the React frontend can multiplex topics
        # by message type (mirrors the moss_context data-packet contract).
        envelope = {"type": self.TOPIC, "data": card.to_dict()}
        payload = json.dumps(envelope).encode("utf-8")
        try:
            await self._room.local_participant.publish_data(
                payload, reliable=True, topic=self.TOPIC
            )
        except Exception:  # noqa: BLE001 — best-effort, don't crash the loop
            logger.exception("DataChannelSink.publish_data failed")


class JsonlSink:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def emit(self, card: Card) -> None:
        line = json.dumps(card.to_dict(), separators=(",", ":")) + "\n"
        # Synchronous append — payload is tiny, blocking time is negligible.
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)


class TranscriptChannelSink:
    """Publish each final transcript line on the `sotto_transcript` data topic.

    Registered via ``MergedTranscript.on_new_final`` (an ``OnNewFinal`` callable), so it streams
    every finalized utterance to the doctor dashboard, mirroring ``DataChannelSink``'s envelope.
    """

    TOPIC = "sotto_transcript"

    def __init__(self, room) -> None:  # rtc.Room — kept untyped to avoid import at module load
        self._room = room

    async def __call__(self, event) -> None:  # event: TranscriptEvent
        envelope = {
            "type": self.TOPIC,
            "data": {
                "timestamp": event.timestamp.isoformat(),
                "speaker": event.speaker,
                "text": event.text,
            },
        }
        payload = json.dumps(envelope).encode("utf-8")
        try:
            await self._room.local_participant.publish_data(
                payload, reliable=True, topic=self.TOPIC
            )
        except Exception:  # noqa: BLE001 — best-effort, don't crash the transcript pipeline
            logger.exception("TranscriptChannelSink.publish_data failed")
