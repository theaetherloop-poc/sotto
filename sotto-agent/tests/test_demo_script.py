"""Tests for the flag-gated deterministic demo cue emitter."""

from __future__ import annotations

from datetime import datetime, timezone

from sotto.demo_script import DemoScriptEmitter
from sotto.sinks import Card
from sotto.transcript import TranscriptEvent


class FakeSink:
    def __init__(self) -> None:
        self.cards: list[Card] = []

    async def emit(self, card: Card) -> None:
        self.cards.append(card)


def _event(speaker: str, text: str) -> TranscriptEvent:
    return TranscriptEvent(timestamp=datetime.now(timezone.utc), speaker=speaker, text=text)


async def test_patient_solvents_line_emits_suggested_questions():
    sink = FakeSink()
    emitter = DemoScriptEmitter([sink])

    await emitter(
        _event("patient", "I run a screen-printing studio, so I'm around inks and solvents all day.")
    )

    assert len(sink.cards) == 1
    card = sink.cards[0]
    assert card.type == "suggested_question"
    assert card.header == "Suggested questions"
    assert "respirator" in card.content


async def test_doctor_labs_line_emits_multi_row_patient_context():
    sink = FakeSink()
    emitter = DemoScriptEmitter([sink])

    await emitter(_event("doctor", "Got it. Let me pull up your recent labs for a moment."))

    assert len(sink.cards) == 1
    card = sink.cards[0]
    assert card.type == "patient_context"
    assert card.header == "Relevant to fatigue"
    assert card.rows is not None and len(card.rows) == 2
    assert {r["source"] for r in card.rows} == {"Labs", "OURA"}
    assert card.rows[0]["heading"] == "Ferritin 18"


async def test_solvents_card_fires_on_any_single_keyword():
    # Any one keyword from the set is enough — no full-sentence match required.
    for line in ("we use a lot of inks here", "it's a small print shop", "fumes from the glue"):
        sink = FakeSink()
        emitter = DemoScriptEmitter([sink])
        await emitter(_event("patient", line))
        assert len(sink.cards) == 1, line
        assert sink.cards[0].type == "suggested_question"


async def test_labs_card_fires_on_alternate_keyword():
    sink = FakeSink()
    emitter = DemoScriptEmitter([sink])
    await emitter(_event("doctor", "Let me check your recent blood panel."))
    assert len(sink.cards) == 1
    assert sink.cards[0].type == "patient_context"


async def test_each_card_fires_at_most_once():
    sink = FakeSink()
    emitter = DemoScriptEmitter([sink])

    await emitter(_event("patient", "around inks and solvents all day"))
    await emitter(_event("patient", "still working with solvents in the back room"))

    assert len(sink.cards) == 1


async def test_non_matching_lines_emit_nothing():
    sink = FakeSink()
    emitter = DemoScriptEmitter([sink])

    await emitter(_event("doctor", "Hi Maya, good to see you again."))
    await emitter(_event("patient", "Honestly, not great. I've been so exhausted lately."))

    assert sink.cards == []


async def test_speaker_must_match_trigger():
    sink = FakeSink()
    emitter = DemoScriptEmitter([sink])

    # The labs card is keyed to the DOCTOR; the same word from the patient must not fire it.
    await emitter(_event("patient", "are my labs okay?"))

    assert sink.cards == []
