"""Tests for CueEngine: parse, debounce, in-flight drop, dedup."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone


from sotto.cue_engine import CueEngine
from sotto.sinks import Card
from sotto.transcript import MergedTranscript, TranscriptEvent


class RecordingSink:
    def __init__(self):
        self.cards: list[Card] = []

    async def emit(self, card: Card) -> None:
        self.cards.append(card)


CARD_JSON = json.dumps(
    {
        "action": "card",
        "type": "suggested_question",
        "content": "Ask about sleep quality over the past 30 days.",
        "rationale": "Patient mentioned fatigue but doctor hasn't probed sleep yet.",
        "triggered_by_speaker": "patient",
        "transcript_snippet": "I've been really tired lately",
    }
)


async def _seed_window(tx: MergedTranscript, text: str = "I've been really tired lately") -> None:
    await tx.add(
        TranscriptEvent(
            timestamp=datetime.now(timezone.utc), speaker="patient", text=text
        )
    )


async def test_action_none_emits_nothing():
    tx = MergedTranscript()
    sink = RecordingSink()
    calls = 0

    async def llm(_msg):
        nonlocal calls
        calls += 1
        return '{"action": "none"}'

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert calls == 1
    assert sink.cards == []


async def test_valid_card_reaches_all_sinks():
    tx = MergedTranscript()
    sink_a = RecordingSink()
    sink_b = RecordingSink()

    async def llm(_msg):
        return CARD_JSON

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink_a, sink_b], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert len(sink_a.cards) == 1
    assert len(sink_b.cards) == 1
    assert sink_a.cards[0].type == "suggested_question"
    assert "sleep" in sink_a.cards[0].content.lower()


async def test_debounce_collapses_rapid_triggers():
    tx = MergedTranscript()
    sink = RecordingSink()
    call_count = 0

    async def llm(_msg):
        nonlocal call_count
        call_count += 1
        return '{"action": "none"}'

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.1)
    await _seed_window(tx)
    # Fire 5 triggers in quick succession.
    for _ in range(5):
        await engine.on_new_final(_ev())
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.3)

    # Only one LLM call after debounce settles.
    assert call_count == 1


async def test_inflight_lock_drops_overlapping_eval():
    tx = MergedTranscript()
    sink = RecordingSink()
    call_count = 0
    release = asyncio.Event()

    async def slow_llm(_msg):
        nonlocal call_count
        call_count += 1
        await release.wait()  # block until released
        return '{"action": "none"}'

    engine = CueEngine(llm_call=slow_llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)

    # First eval — will start the LLM call and block on release.
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.05)
    assert call_count == 1

    # Fire another — should be dropped because in-flight lock is held.
    # We need to bypass debounce: call _evaluate directly.
    await engine._evaluate()
    assert call_count == 1  # still 1, second was dropped

    release.set()
    await asyncio.sleep(0.05)


async def test_dedup_against_recent_card():
    tx = MergedTranscript()
    sink = RecordingSink()
    calls = 0

    async def llm(_msg):
        nonlocal calls
        calls += 1
        return CARD_JSON  # same card every time

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)
    await _seed_window(tx, text="follow-up utterance")
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert calls == 2
    assert len(sink.cards) == 1  # second was deduped


SECOND_CARD_JSON = json.dumps(
    {
        "action": "card",
        "type": "suggested_question",
        "content": "Explore gut history given the antibiotic exposure.",
        "rationale": "New topic opened; gut-immune axis worth probing.",
        "triggered_by_speaker": "patient",
        "transcript_snippet": "my stomach has been off",
    }
)


async def test_low_usefulness_card_is_held_back():
    tx = MergedTranscript()
    sink = RecordingSink()

    # Model self-scored this card as marginal — below the default 0.6 bar, so we hold it.
    low_card = json.dumps(
        {
            "action": "card",
            "type": "suggested_question",
            "content": "Ask about sleep quality over the past 30 days.",
            "rationale": "Marginal, ill-timed.",
            "usefulness": 0.3,
            "triggered_by_speaker": "patient",
            "transcript_snippet": "I've been really tired lately",
        }
    )

    async def llm(_msg):
        return low_card

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert sink.cards == []


async def test_high_usefulness_card_emits():
    tx = MergedTranscript()
    sink = RecordingSink()

    high_card = json.dumps(
        {
            "action": "card",
            "type": "suggested_question",
            "content": "Explore gut history given the antibiotic exposure.",
            "rationale": "Clear gap; well timed.",
            "usefulness": 0.95,
            "triggered_by_speaker": "patient",
            "transcript_snippet": "my stomach has been off",
        }
    )

    async def llm(_msg):
        return high_card

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx, text="my stomach has been off")
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert len(sink.cards) == 1
    assert sink.cards[0].usefulness == 0.95


async def test_no_artificial_cooldown_between_distinct_cards():
    """Two distinct, useful cards back-to-back both emit — there is no time-based gate."""
    tx = MergedTranscript()
    sink = RecordingSink()
    calls = 0

    async def llm(_msg):
        nonlocal calls
        calls += 1
        return CARD_JSON if calls == 1 else SECOND_CARD_JSON

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)
    assert len(sink.cards) == 1

    await _seed_window(tx, text="my stomach has been off")
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)
    assert len(sink.cards) == 2
    assert sink.cards[1].content.startswith("Explore gut history")


async def test_malformed_llm_response_is_ignored():
    tx = MergedTranscript()
    sink = RecordingSink()

    async def llm(_msg):
        return "not even json"

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert sink.cards == []


async def test_llm_call_exception_does_not_crash():
    tx = MergedTranscript()
    sink = RecordingSink()

    async def boom(_msg):
        raise RuntimeError("upstream timeout")

    engine = CueEngine(llm_call=boom, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert sink.cards == []


async def test_ungrounded_snippet_is_dropped():
    """A card whose trigger phrase was never actually said is treated as a hallucination."""
    tx = MergedTranscript()
    sink = RecordingSink()

    hallucinated = json.dumps(
        {
            "action": "card",
            "type": "suggested_question",
            "content": "Ask about recent overseas travel.",
            "rationale": "Sounds relevant.",
            "usefulness": 0.95,
            "triggered_by_speaker": "patient",
            "transcript_snippet": "I just got back from a trip to Thailand",
        }
    )

    async def llm(_msg):
        return hallucinated

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    # Window only contains the fatigue line — the travel snippet was never said.
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert sink.cards == []


async def test_grounded_snippet_passes_with_partial_overlap():
    """Token overlap (not exact quote) is enough — STT phrasing won't match verbatim."""
    tx = MergedTranscript()
    sink = RecordingSink()

    card = json.dumps(
        {
            "action": "card",
            "type": "suggested_question",
            "content": "Probe the fatigue timeline.",
            "rationale": "Patient flagged fatigue.",
            "usefulness": 0.9,
            "triggered_by_speaker": "patient",
            # Reordered/partial vs. the actual "I've been really tired lately".
            "transcript_snippet": "really tired",
        }
    )

    async def llm(_msg):
        return card

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert len(sink.cards) == 1


async def test_card_wrapped_in_markdown_fence_is_parsed():
    tx = MergedTranscript()
    sink = RecordingSink()

    async def llm(_msg):
        return f"```json\n{CARD_JSON}\n```"

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert len(sink.cards) == 1
    assert sink.cards[0].type == "suggested_question"


async def test_metrics_collector_records_eval_and_card():
    from sotto.metrics import MetricsCollector

    tx = MergedTranscript()
    sink = RecordingSink()
    metrics = MetricsCollector(live_publish_interval_s=0.0)
    metrics.start_session(session_id="t")

    async def llm(_msg):
        return CARD_JSON

    engine = CueEngine(
        llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01, metrics=metrics
    )
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    snap = metrics.snapshot()
    assert snap["cue_engine"]["actions"].get("card") == 1
    assert snap["cards"]["by_type"].get("suggested_question") == 1


async def test_metrics_records_dedup_dropped():
    from sotto.metrics import MetricsCollector

    tx = MergedTranscript()
    sink = RecordingSink()
    metrics = MetricsCollector(live_publish_interval_s=0.0)
    metrics.start_session(session_id="t")

    async def llm(_msg):
        return CARD_JSON

    engine = CueEngine(
        llm_call=llm,
        transcript=tx,
        sinks=[sink],
        settle_seconds=0.01,
        metrics=metrics,
    )
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)
    await _seed_window(tx, text="follow-up utterance")
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    snap = metrics.snapshot()
    assert snap["cue_engine"]["dedup_dropped"] == 1
    # First call emits a card; second is deduped into action=none.
    assert snap["cue_engine"]["actions"].get("card") == 1
    assert snap["cue_engine"]["actions"].get("none") == 1


async def test_card_with_surrounding_prose_is_parsed():
    tx = MergedTranscript()
    sink = RecordingSink()

    async def llm(_msg):
        return f"Here is the card:\n{CARD_JSON}\nHope that helps."

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert len(sink.cards) == 1


async def test_retrieve_block_is_injected_into_llm_message():
    tx = MergedTranscript()
    sink = RecordingSink()
    seen: list[str] = []

    async def llm(msg):
        seen.append(msg)
        return '{"action": "none"}'

    async def retrieve(window):
        assert "really tired" in window  # retrieval sees the transcript window
        return "PATIENT_CONTEXT (retrieved):\n- [lab report] TSH high-normal."

    engine = CueEngine(
        llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01, retrieve=retrieve
    )
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert len(seen) == 1
    # The retrieved block is prepended ahead of the recent-cards/transcript sections.
    assert seen[0].startswith("PATIENT_CONTEXT (retrieved):")
    assert "TSH high-normal" in seen[0]
    assert "RECENT_CARDS" in seen[0]
    assert "TRANSCRIPT" in seen[0]


async def test_no_retrieve_omits_patient_context():
    tx = MergedTranscript()
    sink = RecordingSink()
    seen: list[str] = []

    async def llm(msg):
        seen.append(msg)
        return '{"action": "none"}'

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    assert len(seen) == 1
    assert "PATIENT_CONTEXT" not in seen[0]


async def test_retrieve_failure_does_not_block_evaluation():
    tx = MergedTranscript()
    sink = RecordingSink()

    async def llm(_msg):
        return CARD_JSON

    async def boom(_window):
        raise RuntimeError("moss down")

    engine = CueEngine(
        llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01, retrieve=boom
    )
    await _seed_window(tx)
    await engine.on_new_final(_ev())
    await asyncio.sleep(0.1)

    # Retrieval failed, but the cue engine still evaluated and emitted the card.
    assert len(sink.cards) == 1


async def test_doctor_turn_does_not_trigger():
    """A doctor utterance must not trigger evaluation — only completed patient turns do.
    Doctor lines still live in the transcript window as context (added separately)."""
    tx = MergedTranscript()
    sink = RecordingSink()
    calls = 0

    async def llm(_msg):
        nonlocal calls
        calls += 1
        return CARD_JSON

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_doc_ev())
    await asyncio.sleep(0.1)

    assert calls == 0
    assert sink.cards == []


async def test_patient_turn_after_doctor_turn_triggers_once():
    """Only the patient turn drives evaluation, even after a doctor turn arrives."""
    tx = MergedTranscript()
    sink = RecordingSink()
    calls = 0

    async def llm(_msg):
        nonlocal calls
        calls += 1
        return '{"action": "none"}'

    engine = CueEngine(llm_call=llm, transcript=tx, sinks=[sink], settle_seconds=0.01)
    await _seed_window(tx)
    await engine.on_new_final(_doc_ev())  # ignored
    await engine.on_new_final(_ev())  # patient → triggers
    await asyncio.sleep(0.1)

    assert calls == 1


def _ev() -> TranscriptEvent:
    return TranscriptEvent(timestamp=datetime.now(timezone.utc), speaker="patient", text="...")


def _doc_ev() -> TranscriptEvent:
    return TranscriptEvent(timestamp=datetime.now(timezone.utc), speaker="doctor", text="...")
