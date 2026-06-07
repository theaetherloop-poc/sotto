"""Cue engine — debounced LLM-backed evaluator that emits Cards to all sinks."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Awaitable, Callable, Sequence

from .metrics import EvalEvent, MetricsCollector
from .sinks import Card, CueSink
from .transcript import MergedTranscript, TranscriptEvent

logger = logging.getLogger(__name__)

# llm_call(user_message) -> JSON string. The agent entrypoint provides the actual wiring
# (LiveKit Inference LLM with json_object response_format); tests inject a stub.
LLMCall = Callable[[str], Awaitable[str]]


SYSTEM_PROMPT = """You are Sotto, an ambient assistant listening to a live functional-medicine \
consultation between a doctor and a patient. Your role is to push concise context cards to the \
doctor's screen ONLY when there is a clear, useful opportunity.

You will receive the most recent ~30 seconds of merged transcript (with speaker labels) plus a \
list of cards you have already emitted recently. Respond with ONE JSON object in one of these \
two shapes — nothing else, no prose, no code fences.

1) DEFAULT — nothing to add right now:
   {"action": "none"}

2) Emit a card:
   {
     "action": "card",
     "type": "suggested_question" | "patient_context" | "protocol_direction",
     "content": "<<=25-word card body, directly useful to the doctor>>",
     "rationale": "<one sentence on why now>",
     "triggered_by_speaker": "doctor" | "patient",
     "transcript_snippet": "<the trigger phrase, <=15 words>"
   }

Card types:
- suggested_question  — a specific root-cause follow-up the doctor should ask next.
- patient_context     — a fact (labs / wearables / history) relevant right now. Phase 1: invent \
plausibly; later phases will inject real data.
- protocol_direction  — a directional intervention worth exploring (e.g. "consider HPA-axis \
dysregulation").

Rules:
- Bias HARD toward {"action": "none"}. If in doubt, emit none.
- Never restate something the doctor just said.
- Do not repeat or paraphrase a recent card.
- Output ONLY the JSON object. No markdown, no commentary."""


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _extract_json(raw: str) -> dict | None:
    """Parse a JSON object from an LLM reply, tolerating code fences or surrounding prose."""
    text = raw.strip()
    if text.startswith("```"):
        # Strip a leading ```json / ``` fence and the trailing ```.
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Last resort: grab the substring from the first { to the last }.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class CueEngine:
    def __init__(
        self,
        llm_call: LLMCall,
        transcript: MergedTranscript,
        sinks: Sequence[CueSink],
        *,
        window_seconds: int = 30,
        debounce_seconds: float = 0.5,
        recent_card_capacity: int = 3,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._llm = llm_call
        self._transcript = transcript
        self._sinks = list(sinks)
        self._window_seconds = window_seconds
        self._debounce = debounce_seconds
        self._recent: deque[Card] = deque(maxlen=recent_card_capacity)
        self._inflight = asyncio.Lock()
        self._pending: asyncio.Task | None = None
        self._metrics = metrics

    async def on_new_final(self, _event: TranscriptEvent) -> None:
        """Wire this as a MergedTranscript callback. Cancels any pending debounce."""
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._pending = asyncio.create_task(self._debounced_evaluate())

    async def _debounced_evaluate(self) -> None:
        try:
            await asyncio.sleep(self._debounce)
        except asyncio.CancelledError:
            return
        await self._evaluate()

    async def _evaluate(self) -> None:
        if self._inflight.locked():
            logger.info("cue_engine: dropping overlapping evaluation (already in flight)")
            return
        async with self._inflight:
            started = time.monotonic()
            action: str = "none"
            dedup_dropped = False
            try:
                window = await self._transcript.window(self._window_seconds)
                if not window.strip():
                    return

                recent_rendered = (
                    "\n".join(f"- [{c.type}] {c.content}" for c in self._recent) or "(none)"
                )
                user_message = (
                    f"Recent cards already emitted:\n{recent_rendered}\n\n"
                    f"Transcript (last {self._window_seconds}s):\n{window}\n\nDecide."
                )

                try:
                    raw = await self._llm(user_message)
                except Exception:  # noqa: BLE001
                    logger.exception("cue_engine: LLM call failed; skipping")
                    action = "llm_error"
                    return

                card = self._parse(raw)
                if card is None:
                    # _parse returns None for both action=none and malformed JSON; the
                    # warning log inside _parse distinguishes parse errors from clean nones.
                    action = "none"
                    return

                if any(_normalize(c.content) == _normalize(card.content) for c in self._recent):
                    logger.info("cue_engine: dedup — card matches a recent one, skipping")
                    dedup_dropped = True
                    action = "none"
                    return

                self._recent.append(card)
                action = "card"
                for sink in self._sinks:
                    try:
                        await sink.emit(card)
                    except Exception:  # noqa: BLE001
                        logger.exception("cue_engine: sink %s failed", type(sink).__name__)
                if self._metrics is not None:
                    try:
                        await self._metrics.record_card_emitted(card.type)
                    except Exception:  # noqa: BLE001
                        logger.exception("cue_engine: metrics.record_card_emitted failed")
            finally:
                if self._metrics is not None:
                    elapsed_ms = (time.monotonic() - started) * 1000.0
                    try:
                        await self._metrics.record_eval(
                            EvalEvent(
                                action=action,  # type: ignore[arg-type]
                                evaluate_ms=elapsed_ms,
                                dedup_dropped=dedup_dropped,
                            )
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("cue_engine: metrics.record_eval failed")

    @staticmethod
    def _parse(raw: str) -> Card | None:
        obj = _extract_json(raw)
        if obj is None:
            logger.warning("cue_engine: LLM returned non-JSON: %r", raw[:200])
            return None
        action = obj.get("action")
        if action == "none":
            return None
        if action != "card":
            logger.warning("cue_engine: unexpected action=%r", action)
            return None
        try:
            return Card(
                type=obj["type"],
                content=obj["content"],
                rationale=obj["rationale"],
                triggered_by_speaker=obj["triggered_by_speaker"],
                transcript_snippet=obj["transcript_snippet"],
            )
        except KeyError as e:
            logger.warning("cue_engine: card missing field %s; raw=%r", e, raw[:200])
            return None
