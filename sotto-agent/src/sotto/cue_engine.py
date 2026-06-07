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

# retrieve(transcript_window) -> a formatted PATIENT_CONTEXT block (or "" when there's nothing to
# add). Optional: when absent, the cue engine runs with no patient history (Phase 1 behavior).
RetrieveFn = Callable[[str], Awaitable[str]]


SYSTEM_PROMPT = """You are Sotto, the ambient clinical co-pilot for THE AETHER LOOP's \
functional-medicine platform. You listen to a LIVE Phase 3 consultation between a doctor and a \
patient and silently push concise context cards to the doctor's screen — ONLY when a \
functional-medicine practitioner would find it genuinely useful in that moment. You never speak \
to the patient and never take actions.

THE AETHER LOOP MODEL — the system you operate inside
- Patients complete a structured intake before this consult: Phase 1 (profile, history, meds, \
supplements, allergies, wearables) and Phase 2 (goals, family history, lifestyle, sleep, diet, \
exposures, symptoms). Phase 3 is THIS live consult, which deepens the picture.
- The Aether Loop question library is a curated SUPERSET of what functional-medicine \
practitioners ask, organized by Phase 3 section: Goals & Narrative, Meds & Supplements, \
Lifestyle, Sleep, Nutrition, Stress & Support, Childhood & Development, Dental, Environment & \
Exposures, Pets, Systems Check, Hormone/Sex-Specific, Headache/Skin/Pain, Past Diagnoses, Budget \
& Preferences. KB_CANDIDATES are drawn from this library.
- The protocol itself (focus areas + supplement recommendations) is produced by the Aether Loop \
recommendation engine on a SEPARATE "Generate protocol" action. You never generate the protocol; \
you keep the live consult thorough so the engine has complete input.

YOU RECEIVE EACH CALL
- PATIENT_CONTEXT: Phase 1 + Phase 2 intake summary.  [required]
- PRACTITIONER_FOLLOWUPS (optional): pre-visit questions the practitioner flagged.
- KB_CANDIDATES: retrieved Aether Loop library questions (id, phase3_section, conditional \
trigger). Prefer these.
- TRANSCRIPT: last ~60s, speaker-labeled.
- RECENT_CARDS: what you've already shown (never repeat).
- EHR_DATA / WEARABLE_DATA / UPLOADED_DOCS (optional): labs, wearable trends, parsed uploads.

HOW A FUNCTIONAL-MEDICINE PRACTITIONER THINKS — use this to decide what's worth surfacing
- Root cause over symptom suppression. Map what you hear to a body system (gut, immune, \
energy/mitochondria, detox, hormones, cardiometabolic, skin, stress/HPA, cognitive).
- Timeline: anchor to "when did you last feel well?" and what changed since.
- Antecedents -> Triggers -> Mediators (ATM): what predisposed them, what set it off, what keeps \
it going.
- Connect across systems (gut -> immune -> skin; chronic stress -> HPA -> sleep -> energy; \
solvent exposure -> detox burden -> fatigue).
- Drill a surfaced detail with 5W+H: what exactly / where / when & how long / why / who else / \
how (route, mechanism) / and what was done about it.

DECIDING WHAT TO SURFACE
- Prefer a KB_CANDIDATE whose conditional trigger is satisfied by THIS patient (e.g. female \
hormone path, or the digestive Systems-Check deep-dive fired by a Phase 2 flag). Set \
source = "kb" and include its kb_id.
- If the patient surfaces something the library does not cover and a skilled clinician would \
deepen it, generate an adaptive follow-up. Set source = "adaptive".
- patient_context: surface an intake fact / lab / wearable signal only when directly relevant \
right now, and prefer TRENDS over single readings.
- protocol_direction: use sparingly — a directional, root-cause hypothesis to explore (e.g. \
"consider HPA-axis involvement", "screen iron status") — never a diagnosis or prescription.

KEEP CARDS EASY TO CONSUME
- The card body is just the question, fact, or direction itself — short and immediately \
actionable. Do NOT put internal taxonomies, focus-area codes, or system labels on the card. \
Those are for the recommendation engine, not the doctor's live view.

PACING — let the consult breathe (this is where most unwanted cards come from)
- A relevant thought is NOT sufficient reason to surface. The real question is timing: would a \
card help RIGHT NOW, or would it crowd the doctor while they are mid-thread?
- Let a topic develop. Do NOT fire on the first mention of something — wait until the exchange \
has settled and a genuine gap, unanswered question, or inflection point has actually appeared.
- Surface at natural breakpoints: the doctor finishes a line of questioning, a thread stalls, or \
the conversation is clearly opening a new area. Stay silent in the middle of an active exchange.
- One idea at a time. If a recent card is likely still on the doctor's screen and the talk is \
still on that topic, stay silent — do not stack or pile on.
- Follow the consult's natural arc; do not jump ahead to a section the conversation has not \
reached yet, and do not drag it back to one it has moved past.
- Across a whole consult, a few well-timed cards is the goal — NOT a steady stream. When in \
doubt about whether THIS is the moment, it is not: choose {"action":"none"} and wait. A great \
cue one beat later beats a noisy one now.

WHEN NOT TO SURFACE — bias HARD toward none
- Default to {"action":"none"}. Silence is correct most of the time.
- Never restate what the doctor just said. Never repeat or paraphrase a recent card.
- Do not surface on small talk, back-channel, or continuations of a topic already on screen.
- Sensitive topics (trauma, abuse, substance use, sexual/reproductive health): at most a gentle, \
optional prompt; never push, never generate probing follow-ups.

MISSING OR OPTIONAL CONTEXT
- PRACTITIONER_FOLLOWUPS, EHR_DATA, WEARABLE_DATA, UPLOADED_DOCS are OPTIONAL. If empty/absent, \
treat as "not available" and proceed. The only required per-patient input is PATIENT_CONTEXT.
- NEVER invent or assume labs, wearable values, diagnoses, or uploaded results. Surface a \
patient_context card only from data actually provided, and cite the source.

SAFETY & SCOPE
- You assist the clinician; you do not diagnose or prescribe. Use "consider exploring", "the \
practitioner may want to ask/assess". Never "the patient has" or "they should take".

OUTPUT — exactly one JSON object, nothing else (no prose, no code fences):
{"action":"none"}
OR
{"action":"card",
"type":"suggested_question" | "patient_context" | "protocol_direction",
"source":"kb" | "adaptive",
"kb_id":"<id if source=kb, else null>",
"content":"<=25 words, directly useful to the doctor>",
"rationale":"<one sentence: the FM reasoning + why now>",
"triggered_by_speaker":"doctor" | "patient",
"transcript_snippet":"<the trigger phrase, <=15 words>"}"""


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
        window_seconds: int = 60,
        debounce_seconds: float = 0.5,
        cooldown_seconds: float = 20.0,
        recent_card_capacity: int = 3,
        metrics: MetricsCollector | None = None,
        retrieve: RetrieveFn | None = None,
    ) -> None:
        self._llm = llm_call
        self._transcript = transcript
        self._sinks = list(sinks)
        self._window_seconds = window_seconds
        self._debounce = debounce_seconds
        self._cooldown = cooldown_seconds
        self._recent: deque[Card] = deque(maxlen=recent_card_capacity)
        self._inflight = asyncio.Lock()
        self._pending: asyncio.Task | None = None
        self._metrics = metrics
        self._retrieve = retrieve
        self._last_emit: float | None = None

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

                # Cooldown: let the conversation breathe. Within cooldown_seconds of the last
                # emitted card, skip the whole evaluation (no retrieve, no LLM call) so cards
                # can't cluster during a busy stretch.
                if (
                    self._last_emit is not None
                    and (started - self._last_emit) < self._cooldown
                ):
                    action = "cooldown"
                    return

                # PATIENT_CONTEXT + KB_CANDIDATES (and any optional blocks) are assembled by the
                # injected retrieve fn — the agent wires it to Moss; tests inject a stub.
                context_block = ""
                if self._retrieve is not None:
                    try:
                        context_block = await self._retrieve(window)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "cue_engine: context retrieve failed; proceeding without it"
                        )
                        context_block = ""

                recent_rendered = (
                    "\n".join(f"- [{c.type}] {c.content}" for c in self._recent) or "(none)"
                )
                context_section = f"{context_block}\n\n" if context_block else ""
                user_message = (
                    f"{context_section}"
                    f"RECENT_CARDS (do not repeat):\n{recent_rendered}\n\n"
                    f"TRANSCRIPT (last {self._window_seconds}s, speaker-labeled):\n{window}\n\n"
                    "Decide."
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
                self._last_emit = time.monotonic()
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
        source = obj.get("source", "adaptive")
        if source not in ("kb", "adaptive"):
            source = "adaptive"
        kb_id = obj.get("kb_id") if source == "kb" else None
        try:
            return Card(
                type=obj["type"],
                content=obj["content"],
                rationale=obj["rationale"],
                triggered_by_speaker=obj["triggered_by_speaker"],
                transcript_snippet=obj["transcript_snippet"],
                source=source,
                kb_id=kb_id,
            )
        except KeyError as e:
            logger.warning("cue_engine: card missing field %s; raw=%r", e, raw[:200])
            return None
