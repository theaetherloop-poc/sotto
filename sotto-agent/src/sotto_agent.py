"""Sotto — ambient agent entrypoint.

Joins a LiveKit room, subscribes to the doctor and patient audio tracks, transcribes each via
Deepgram (LiveKit Inference), feeds the merged transcript to the cue engine, and emits text-only
cue cards.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import AgentServer, AutoSubscribe, JobContext, llm, stt
from livekit.agents.inference import LLM as InferenceLLM
from livekit.agents.inference import STT as InferenceSTT

from sotto.cue_engine import SYSTEM_PROMPT, CueEngine
from sotto.metrics import (
    JsonlMetricsEventSink,
    JsonlMetricsSessionSink,
    LLMEvent,
    MetricsCollector,
    STTEvent,
)
from sotto.sinks import DataChannelSink, JsonlSink, StdoutSink
from sotto.telemetry import setup_tracing
from sotto.transcript import MergedTranscript, TranscriptEvent, TranscriptFileWriter

load_dotenv(".env.local")
load_dotenv()

logger = logging.getLogger("sotto")

ALLOWED_SPEAKERS = ("doctor", "patient")
# Medical-tuned STT: vocabulary tuned for drugs, anatomy, labs — relevant for functional
# medicine consults. English-only (en, en-US, en-GB, etc. — see Deepgram docs).
STT_MODEL = "deepgram/nova-3-medical"
STT_LANGUAGE = "en"
# Reasoning model. Cheaper than gpt-4.1-mini at this token volume, with noticeably better
# judgment on the "emit or stay silent" decision. Uses `reasoning_effort` instead of
# `temperature` (temperature is not supported on reasoning models).
LLM_MODEL = "openai/gpt-5-mini"
LLM_REASONING_EFFORT = "low"

server = AgentServer()


def speaker_for(identity: str) -> str | None:
    """Map a participant identity to its consult role.

    The frontend mints unique identities like ``doctor-a1b2c3`` (unique so LiveKit never kicks
    duplicates), carrying the role as the prefix. Returns the role, or None to ignore.
    """
    for role in ALLOWED_SPEAKERS:
        if identity == role or identity.startswith(role + "-"):
            return role
    return None


def _attach_stt_plugin_metrics(stt_instance, metrics: MetricsCollector | None, loop) -> None:
    """Bridge the STT plugin's ``metrics_collected`` event into the MetricsCollector.

    We only use STT plugin metrics to enrich ``audio_duration_s``; latency is measured directly
    in ``_transcribe_track`` because streaming STT reports ``duration=0``.
    """
    if metrics is None:
        return
    try:
        @stt_instance.on("metrics_collected")
        def _on_stt_metrics(ev) -> None:  # ev: STTMetrics
            # No speaker context at the plugin level (one plugin per track). The audio duration
            # is summed into the session total; we ignore zero-usage connection events.
            audio = getattr(ev, "audio_duration", None)
            if audio is None or audio <= 0:
                return
            metrics._stt_audio_duration_s += float(audio)  # noqa: SLF001 — internal aggregation

    except Exception:  # noqa: BLE001
        logger.warning("could not attach STT metrics listener", exc_info=True)


def _attach_llm_plugin_metrics(
    llm_instance, metrics: MetricsCollector | None, loop: asyncio.AbstractEventLoop
) -> None:
    """Bridge the LLM plugin's ``metrics_collected`` event into the MetricsCollector."""
    if metrics is None:
        return

    def _coerce_ms(seconds_val) -> float | None:
        if seconds_val is None:
            return None
        try:
            return float(seconds_val) * 1000.0
        except (TypeError, ValueError):
            return None

    try:
        @llm_instance.on("metrics_collected")
        def _on_llm_metrics(ev) -> None:  # ev: LLMMetrics
            event = LLMEvent(
                ttft_ms=_coerce_ms(getattr(ev, "ttft", None)),
                duration_ms=_coerce_ms(getattr(ev, "duration", 0)) or 0.0,
                prompt_tokens=getattr(ev, "prompt_tokens", None),
                completion_tokens=getattr(ev, "completion_tokens", None),
                total_tokens=getattr(ev, "total_tokens", None),
                cached_tokens=getattr(ev, "prompt_cached_tokens", None),
                tokens_per_second=getattr(ev, "tokens_per_second", None),
            )
            asyncio.run_coroutine_threadsafe(metrics.record_llm(event), loop)
    except Exception:  # noqa: BLE001
        logger.warning("could not attach LLM metrics listener", exc_info=True)


def _build_llm_caller(llm_instance: InferenceLLM):
    """Wrap the Inference LLM into the `LLMCall` signature the CueEngine expects."""

    async def call(user_message: str) -> str:
        chat_ctx = llm.ChatContext()
        chat_ctx.add_message(role="system", content=SYSTEM_PROMPT)
        chat_ctx.add_message(role="user", content=user_message)
        # NOTE: livekit-agents 1.5.x's chat(response_format=...) only accepts a Pydantic
        # model and raises on the OpenAI-style {"type": "json_object"} dict, so we rely on
        # the system prompt to enforce JSON and parse defensively in CueEngine._parse.
        response = await llm_instance.chat(
            chat_ctx=chat_ctx,
            extra_kwargs={"reasoning_effort": LLM_REASONING_EFFORT},
        ).collect()
        return response.text

    return call


async def _transcribe_track(
    track: rtc.Track,
    speaker: str,
    transcript: MergedTranscript,
    metrics: MetricsCollector | None = None,
) -> None:
    """Run streaming STT on a single audio track and push final transcripts to the merged log."""
    logger.info("starting STT stream for speaker=%s track_sid=%s", speaker, track.sid)
    audio_stream = rtc.AudioStream.from_track(track=track, sample_rate=16000, num_channels=1)
    stt_instance = InferenceSTT.from_model_string(STT_MODEL)
    _attach_stt_plugin_metrics(stt_instance, metrics, asyncio.get_running_loop())
    stt_stream = stt_instance.stream(language=STT_LANGUAGE)

    # Updated on every audio frame; FINAL_TRANSCRIPT compares against this for STT latency.
    last_audio_push_mono: float = 0.0

    async def _pump_audio() -> None:
        nonlocal last_audio_push_mono
        try:
            async for ev in audio_stream:
                last_audio_push_mono = time.monotonic()
                stt_stream.push_frame(ev.frame)
        except Exception:  # noqa: BLE001
            logger.exception("audio pump failed for speaker=%s", speaker)
            if metrics is not None:
                metrics.record_stt_error()
        finally:
            stt_stream.end_input()

    pump = asyncio.create_task(_pump_audio(), name=f"audio_pump_{speaker}")
    try:
        async for ev in stt_stream:
            if ev.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                text = ev.alternatives[0].text.strip() if ev.alternatives else ""
                if not text:
                    continue
                event = TranscriptEvent(
                    timestamp=datetime.now(timezone.utc), speaker=speaker, text=text
                )
                logger.info(event.render())
                if metrics is not None and last_audio_push_mono > 0:
                    latency_ms = (time.monotonic() - last_audio_push_mono) * 1000.0
                    try:
                        await metrics.record_stt(
                            STTEvent(speaker=speaker, latency_ms=latency_ms, streamed=True)
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("metrics.record_stt failed")
                await transcript.add(event)
            elif ev.type == stt.SpeechEventType.INTERIM_TRANSCRIPT:
                # noisy — only enable for debugging
                logger.debug(
                    "interim[%s]: %s",
                    speaker,
                    ev.alternatives[0].text if ev.alternatives else "",
                )
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("STT stream failed for speaker=%s", speaker)
        if metrics is not None:
            metrics.record_stt_error()
    finally:
        pump.cancel()
        try:
            await stt_stream.aclose()
        except Exception:  # noqa: BLE001
            pass


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info("sotto agent joining room — job_id=%s", ctx.job.id)
    # Opt-in OpenTelemetry. No-op if no telemetry env vars are configured.
    setup_tracing()
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    transcript = MergedTranscript()

    metrics = MetricsCollector(
        sinks=[
            JsonlMetricsEventSink(Path("logs/sotto-metrics.jsonl")),
            JsonlMetricsSessionSink(Path("logs/sotto-sessions.jsonl")),
        ]
    )
    metrics.start_session(
        session_id=str(uuid.uuid4()),
        room_name=getattr(ctx.room, "name", None),
        job_id=ctx.job.id,
    )

    # Capture the room's disconnect reason (when available) so it ends up in the session
    # summary. The shutdown callback below writes the summary regardless of how the session
    # ends (clean disconnect, agent process kill, exception in entrypoint, etc.).
    disconnect_reason: dict[str, str | None] = {"value": None}

    async def _finalize_metrics() -> None:
        try:
            summary = await metrics.end_session(disconnect_reason=disconnect_reason["value"])
            logger.info(
                "session summary — transcripts=%d cards=%d llm_calls=%d "
                "stt_p95_ms=%s llm_ttft_p95_ms=%s",
                summary["transcripts"]["total"],
                summary["cards"]["total"],
                summary["llm"]["calls"],
                summary["stt"]["p95_ms"],
                summary["llm"]["ttft"]["p95_ms"],
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to finalize metrics session")

    ctx.add_shutdown_callback(_finalize_metrics)

    llm_instance = InferenceLLM(model=LLM_MODEL)
    _attach_llm_plugin_metrics(llm_instance, metrics, asyncio.get_running_loop())

    sinks = [
        StdoutSink(),
        DataChannelSink(ctx.room),
        JsonlSink(Path("logs/sotto-cues.jsonl")),
    ]
    cue_engine = CueEngine(
        llm_call=_build_llm_caller(llm_instance),
        transcript=transcript,
        sinks=sinks,
        metrics=metrics,
    )
    transcript.on_new_final(cue_engine.on_new_final)
    transcript.on_new_final(TranscriptFileWriter(Path("logs/sotto-transcript.jsonl")))

    track_tasks: dict[str, asyncio.Task] = {}

    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            logger.info("ignoring non-audio track from %s", participant.identity)
            return
        speaker = speaker_for(participant.identity)
        if speaker is None:
            logger.warning(
                "ignoring track from unknown identity=%r (expected prefix one of %s)",
                participant.identity,
                ALLOWED_SPEAKERS,
            )
            return
        if speaker in track_tasks and not track_tasks[speaker].done():
            logger.info("speaker=%s already has an active STT task; skipping", speaker)
            return
        task = asyncio.create_task(
            _transcribe_track(track, speaker, transcript, metrics), name=f"stt_{speaker}"
        )
        track_tasks[speaker] = task

    def on_participant_connected(participant: rtc.RemoteParticipant) -> None:
        metrics.record_participant_join(
            identity=participant.identity, role=speaker_for(participant.identity)
        )

    def on_participant_disconnected(participant: rtc.RemoteParticipant) -> None:
        metrics.record_participant_leave(participant.identity)

    ctx.room.on("track_subscribed", on_track_subscribed)
    ctx.room.on("participant_connected", on_participant_connected)
    ctx.room.on("participant_disconnected", on_participant_disconnected)

    # If participants joined before the agent attached its handler, pick up their tracks.
    for participant in ctx.room.remote_participants.values():
        if speaker_for(participant.identity) is None:
            continue
        metrics.record_participant_join(
            identity=participant.identity, role=speaker_for(participant.identity)
        )
        for publication in participant.track_publications.values():
            if publication.track is not None and publication.kind == rtc.TrackKind.KIND_AUDIO:
                on_track_subscribed(publication.track, publication, participant)

    disconnected = asyncio.Event()

    def _on_disconnected(*args, **_kwargs) -> None:
        reason = args[0] if args else None
        disconnect_reason["value"] = str(reason) if reason is not None else None
        logger.info("room disconnected — reason=%s", disconnect_reason["value"])
        disconnected.set()

    ctx.room.on("disconnected", _on_disconnected)

    logger.info(
        "sotto ready — waiting for participants with identity in %s", ALLOWED_SPEAKERS
    )
    await disconnected.wait()

    for task in track_tasks.values():
        task.cancel()
    # Session summary is written by the shutdown callback registered above — it runs
    # regardless of how this entrypoint exits (clean disconnect, Ctrl+C, exception).


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    agents.cli.run_app(server)
