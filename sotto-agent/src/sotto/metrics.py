"""Observability metrics for the Sotto agent.

Captures per-event STT/LLM/cue-engine measurements and aggregates a live session snapshot.
Pure-Python; the agent entrypoint wires real STT/LLM plugin events into ``MetricsCollector``,
and tests can drive it directly.

Three sinks (mirroring the cue-card sinks):

* ``JsonlMetricsEventSink``    — appends every raw event to ``logs/sotto-metrics.jsonl``.
* ``JsonlMetricsSessionSink``  — writes the per-session summary to ``logs/sotto-sessions.jsonl``
  when the session ends.
* ``DataChannelMetricsSink``   — publishes a throttled snapshot to the LiveKit data channel
  on topic ``sotto_metrics`` so the doctor dashboard can render a live observability panel.

The collector is entirely additive — if you pass no sinks the existing flow is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol

logger = logging.getLogger(__name__)


CueAction = Literal["card", "none", "parse_error", "llm_error"]

# Rolling window used to compute p50/p95 for STT and LLM. Bounded so memory stays flat on
# long sessions; large enough to be meaningful in a typical 20-minute consult.
_LATENCY_WINDOW = 100

# Minimum gap between live-snapshot data-channel publishes. Prevents flooding the dashboard
# when many transcript events arrive in quick succession.
_LIVE_PUBLISH_INTERVAL_S = 0.75


@dataclass
class STTEvent:
    speaker: str
    latency_ms: float
    audio_duration_s: float | None = None
    streamed: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "stt",
            "speaker": self.speaker,
            "latency_ms": round(self.latency_ms, 2),
            "audio_duration_s": (
                round(self.audio_duration_s, 3) if self.audio_duration_s is not None else None
            ),
            "streamed": self.streamed,
            "timestamp": self.timestamp,
        }


@dataclass
class LLMEvent:
    ttft_ms: float | None
    duration_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cached_tokens: int | None
    tokens_per_second: float | None
    error: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "llm",
            "ttft_ms": None if self.ttft_ms is None else round(self.ttft_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "tokens_per_second": (
                None if self.tokens_per_second is None else round(self.tokens_per_second, 2)
            ),
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class EvalEvent:
    action: CueAction
    evaluate_ms: float
    dedup_dropped: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "eval",
            "action": self.action,
            "evaluate_ms": round(self.evaluate_ms, 2),
            "dedup_dropped": self.dedup_dropped,
            "timestamp": self.timestamp,
        }


class MetricsSink(Protocol):
    async def emit_event(self, event: dict[str, Any]) -> None: ...
    async def emit_snapshot(self, snapshot: dict[str, Any]) -> None: ...
    async def emit_session(self, summary: dict[str, Any]) -> None: ...


class JsonlMetricsEventSink:
    """Append-only jsonl of every raw metrics event. Snapshots/sessions are no-ops here."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def emit_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)

    async def emit_snapshot(self, snapshot: dict[str, Any]) -> None:
        return None

    async def emit_session(self, summary: dict[str, Any]) -> None:
        return None


class JsonlMetricsSessionSink:
    """Append-only jsonl of one record per completed session. Events are no-ops here."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def emit_event(self, event: dict[str, Any]) -> None:
        return None

    async def emit_snapshot(self, snapshot: dict[str, Any]) -> None:
        return None

    async def emit_session(self, summary: dict[str, Any]) -> None:
        line = json.dumps(summary, separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)


class DataChannelMetricsSink:
    """Publish throttled live snapshots to the room on topic ``sotto_metrics``."""

    TOPIC = "sotto_metrics"

    def __init__(self, room) -> None:  # rtc.Room; untyped to avoid import at module load
        self._room = room

    async def emit_event(self, event: dict[str, Any]) -> None:
        return None

    async def emit_snapshot(self, snapshot: dict[str, Any]) -> None:
        envelope = {"type": self.TOPIC, "data": snapshot}
        payload = json.dumps(envelope).encode("utf-8")
        try:
            await self._room.local_participant.publish_data(
                payload, reliable=False, topic=self.TOPIC
            )
        except Exception:  # noqa: BLE001
            logger.exception("DataChannelMetricsSink.publish_data failed")

    async def emit_session(self, summary: dict[str, Any]) -> None:
        # Publish the final summary as a snapshot too so the dashboard sees the end state.
        await self.emit_snapshot({**summary, "final": True})


def _percentile(values: Iterable[float], p: float) -> float | None:
    samples = sorted(values)
    if not samples:
        return None
    # statistics.quantiles needs >=2 points; for a single sample, just return it.
    if len(samples) == 1:
        return samples[0]
    k = max(0, min(len(samples) - 1, int(round((p / 100.0) * (len(samples) - 1)))))
    return samples[k]


class MetricsCollector:
    """Aggregates STT/LLM/eval events and exposes a serializable snapshot.

    Lifecycle: ``start_session`` once, ``record_*`` as events flow, ``end_session`` once.
    The collector publishes live snapshots to its sinks after each event (rate-limited) and
    a final session summary on ``end_session``.
    """

    def __init__(
        self,
        sinks: Iterable[MetricsSink] = (),
        *,
        live_publish_interval_s: float = _LIVE_PUBLISH_INTERVAL_S,
        clock: callable = time.monotonic,
    ) -> None:
        self._sinks: list[MetricsSink] = list(sinks)
        self._live_interval = live_publish_interval_s
        self._clock = clock

        self._session_id: str | None = None
        self._room_name: str | None = None
        self._job_id: str | None = None
        self._started_at_iso: str | None = None
        self._started_at_mono: float | None = None
        self._ended_at_iso: str | None = None
        self._disconnect_reason: str | None = None

        # Counts.
        self._transcripts_by_speaker: dict[str, int] = {}
        self._cards_by_type: dict[str, int] = {}
        self._eval_actions: dict[str, int] = {}
        self._participants_seen: dict[str, dict[str, Any]] = {}

        # STT.
        self._stt_latencies_ms: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._stt_audio_duration_s = 0.0
        self._stt_errors = 0

        # LLM.
        self._llm_ttft_ms: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._llm_duration_ms: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._llm_prompt_tokens = 0
        self._llm_completion_tokens = 0
        self._llm_total_tokens = 0
        self._llm_cached_tokens = 0
        self._llm_calls = 0
        self._llm_errors = 0

        # Engine.
        self._eval_ms: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._eval_dedup_dropped = 0

        self._last_publish_mono: float = 0.0

    # ---------- lifecycle ----------

    def start_session(
        self, *, session_id: str, room_name: str | None = None, job_id: str | None = None
    ) -> None:
        self._session_id = session_id
        self._room_name = room_name
        self._job_id = job_id
        self._started_at_iso = datetime.now(timezone.utc).isoformat()
        self._started_at_mono = self._clock()

    def record_participant_join(self, identity: str, role: str | None) -> None:
        self._participants_seen[identity] = {
            "identity": identity,
            "role": role,
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "left_at": None,
        }

    def record_participant_leave(self, identity: str) -> None:
        entry = self._participants_seen.get(identity)
        if entry is not None:
            entry["left_at"] = datetime.now(timezone.utc).isoformat()

    async def end_session(self, *, disconnect_reason: str | None = None) -> dict[str, Any]:
        self._disconnect_reason = disconnect_reason
        self._ended_at_iso = datetime.now(timezone.utc).isoformat()
        summary = self.snapshot(final=True)
        for sink in self._sinks:
            try:
                await sink.emit_session(summary)
            except Exception:  # noqa: BLE001
                logger.exception("metrics sink %s emit_session failed", type(sink).__name__)
        return summary

    # ---------- recording ----------

    async def record_stt(self, event: STTEvent) -> None:
        self._stt_latencies_ms.append(event.latency_ms)
        if event.audio_duration_s is not None:
            self._stt_audio_duration_s += event.audio_duration_s
        self._transcripts_by_speaker[event.speaker] = (
            self._transcripts_by_speaker.get(event.speaker, 0) + 1
        )
        await self._emit_event(event.to_dict())
        await self._maybe_publish_snapshot()

    def record_stt_error(self) -> None:
        self._stt_errors += 1

    async def record_llm(self, event: LLMEvent) -> None:
        if event.error:
            self._llm_errors += 1
        else:
            self._llm_calls += 1
            if event.ttft_ms is not None:
                self._llm_ttft_ms.append(event.ttft_ms)
            self._llm_duration_ms.append(event.duration_ms)
            self._llm_prompt_tokens += event.prompt_tokens or 0
            self._llm_completion_tokens += event.completion_tokens or 0
            self._llm_total_tokens += event.total_tokens or 0
            self._llm_cached_tokens += event.cached_tokens or 0
        await self._emit_event(event.to_dict())
        await self._maybe_publish_snapshot()

    async def record_eval(self, event: EvalEvent) -> None:
        self._eval_ms.append(event.evaluate_ms)
        self._eval_actions[event.action] = self._eval_actions.get(event.action, 0) + 1
        if event.dedup_dropped:
            self._eval_dedup_dropped += 1
        await self._emit_event(event.to_dict())
        await self._maybe_publish_snapshot()

    async def record_card_emitted(self, card_type: str) -> None:
        self._cards_by_type[card_type] = self._cards_by_type.get(card_type, 0) + 1
        await self._maybe_publish_snapshot(force=True)

    # ---------- snapshot ----------

    def snapshot(self, *, final: bool = False) -> dict[str, Any]:
        elapsed_s: float | None = None
        if self._started_at_mono is not None:
            elapsed_s = round(self._clock() - self._started_at_mono, 3)

        def _agg(samples: Iterable[float]) -> dict[str, Any]:
            xs = list(samples)
            if not xs:
                return {"count": 0, "p50_ms": None, "p95_ms": None, "max_ms": None}
            return {
                "count": len(xs),
                "p50_ms": round(_percentile(xs, 50) or 0, 2),
                "p95_ms": round(_percentile(xs, 95) or 0, 2),
                "max_ms": round(max(xs), 2),
                "mean_ms": round(statistics.fmean(xs), 2),
            }

        return {
            "session_id": self._session_id,
            "room_name": self._room_name,
            "job_id": self._job_id,
            "started_at": self._started_at_iso,
            "ended_at": self._ended_at_iso,
            "elapsed_s": elapsed_s,
            "final": final,
            "disconnect_reason": self._disconnect_reason,
            "participants": list(self._participants_seen.values()),
            "transcripts": {
                "by_speaker": dict(self._transcripts_by_speaker),
                "total": sum(self._transcripts_by_speaker.values()),
            },
            "cards": {
                "by_type": dict(self._cards_by_type),
                "total": sum(self._cards_by_type.values()),
            },
            "stt": {
                **_agg(self._stt_latencies_ms),
                "audio_duration_s": round(self._stt_audio_duration_s, 3),
                "errors": self._stt_errors,
            },
            "llm": {
                "ttft": _agg(self._llm_ttft_ms),
                "duration": _agg(self._llm_duration_ms),
                "calls": self._llm_calls,
                "errors": self._llm_errors,
                "tokens": {
                    "prompt": self._llm_prompt_tokens,
                    "completion": self._llm_completion_tokens,
                    "total": self._llm_total_tokens,
                    "cached": self._llm_cached_tokens,
                },
            },
            "cue_engine": {
                **_agg(self._eval_ms),
                "actions": dict(self._eval_actions),
                "dedup_dropped": self._eval_dedup_dropped,
            },
        }

    # ---------- internals ----------

    async def _emit_event(self, event: dict[str, Any]) -> None:
        for sink in self._sinks:
            try:
                await sink.emit_event(event)
            except Exception:  # noqa: BLE001
                logger.exception("metrics sink %s emit_event failed", type(sink).__name__)

    async def _maybe_publish_snapshot(self, *, force: bool = False) -> None:
        now = self._clock()
        if not force and (now - self._last_publish_mono) < self._live_interval:
            return
        self._last_publish_mono = now
        snapshot = self.snapshot()
        for sink in self._sinks:
            try:
                await sink.emit_snapshot(snapshot)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "metrics sink %s emit_snapshot failed", type(sink).__name__
                )


__all__ = [
    "CueAction",
    "DataChannelMetricsSink",
    "EvalEvent",
    "JsonlMetricsEventSink",
    "JsonlMetricsSessionSink",
    "LLMEvent",
    "MetricsCollector",
    "MetricsSink",
    "STTEvent",
]


# Avoid unused-import warnings; asyncio kept for sink Protocol consumers awaiting.
_ = asyncio
