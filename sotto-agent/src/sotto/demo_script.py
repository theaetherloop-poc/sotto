"""Flag-gated deterministic demo cues — for scripted product demos ONLY.

When ``SOTTO_DEMO_SCRIPT`` is set, the agent registers :class:`DemoScriptEmitter` on the merged
transcript INSTEAD of the LLM cue engine. A known walkthrough then surfaces a fixed set of cards
at exact moments. This exists because the live LLM path is non-deterministic and some demo
triggers land on *doctor* turns the cue engine never evaluates (it only fires on patient turns).

Temporary: unset the flag (or delete this module + its wiring in ``sotto_agent.py``) to return to
the live LLM engine. The cards mirror the UI mockup's Screen 1 exactly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from .sinks import Card, CueSink
from .transcript import TranscriptEvent

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass
class _ScriptedCue:
    """A single scripted card and the transcript condition that fires it."""

    id: str
    speaker: str
    # Fire when ANY of these (already-normalized) keywords/phrases appears anywhere in the line —
    # not the whole sentence. Substring match, so "solvent" also catches "solvents" and "lab"
    # catches "labs". Kept broad so the trigger survives paraphrasing and STT variance; only one
    # keyword needs to land.
    keywords: tuple[str, ...]
    card: Card


def _build_script() -> list[_ScriptedCue]:
    """The two demo cards, keyed to the scripted Maya Chen consult."""
    return [
        # Patient: "...I run a screen-printing studio, so I'm around inks and solvents all day."
        _ScriptedCue(
            id="solvents-followups",
            speaker="patient",
            keywords=(
                "solvent",
                "ink",
                "screen-print",
                "screen print",
                "printing studio",
                "print shop",
                "glue",
            ),
            card=Card(
                type="suggested_question",
                header="Suggested questions",
                content=(
                    "Which solvents or inks? · breathing or skin? · hours/years? · "
                    "respirator? · headaches after work?"
                ),
                rationale="",
                triggered_by_speaker="patient",
                transcript_snippet="inks and solvents",
                source="adaptive",
            ),
        ),
        # Doctor: "Got it. Let me pull up your recent labs for a moment."
        _ScriptedCue(
            id="labs-context",
            speaker="doctor",
            keywords=(
                "lab",
                "blood panel",
                "blood work",
                "bloodwork",
                "pull up your",
                "recent results",
                "ferritin",
            ),
            card=Card(
                type="patient_context",
                header="Relevant to fatigue",
                content="",
                rows=[
                    {
                        "heading": "Ferritin 18",
                        "detail": "↓ 52→41→34→18 / 14mo",
                        "source": "Labs",
                        "tone": "red",
                    },
                    {
                        "heading": "Sleep 5.5h",
                        "detail": "was 7.1h · HRV ↓21%",
                        "source": "OURA",
                        "tone": "neutral",
                    },
                ],
                rationale="",
                triggered_by_speaker="doctor",
                transcript_snippet="pull up your recent labs",
                source="adaptive",
            ),
        ),
    ]


class DemoScriptEmitter:
    """Emit pre-authored cards on phrase match. Registered as a ``MergedTranscript`` callback.

    Each scripted card fires at most once per session (deduped by id), and matches on either
    speaker — so a doctor-triggered card works, which the LLM cue engine could not do.
    """

    def __init__(self, sinks: Sequence[CueSink]) -> None:
        self._sinks = list(sinks)
        self._script = _build_script()
        self._fired: set[str] = set()

    async def __call__(self, event: TranscriptEvent) -> None:
        text = _normalize(event.text)
        for cue in self._script:
            if cue.id in self._fired:
                continue
            if event.speaker != cue.speaker:
                continue
            if not any(kw in text for kw in cue.keywords):
                continue
            self._fired.add(cue.id)
            logger.info("demo_script: emitting %r on %s line", cue.id, event.speaker)
            for sink in self._sinks:
                try:
                    await sink.emit(cue.card)
                except Exception:  # noqa: BLE001 — best-effort, never crash the pipeline
                    logger.exception("demo_script: sink %s failed", type(sink).__name__)
