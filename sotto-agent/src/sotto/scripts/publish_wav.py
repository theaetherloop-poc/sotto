"""Join a room as a given identity and publish a WAV file as the microphone track.

Used for scripted/reproducible scenarios when humans aren't available to speak into mics.

Usage:
    uv run python -m sotto.scripts.publish_wav \\
        --identity doctor --room sotto-test --wav fixtures/doctor.wav

The WAV must be PCM (16-bit signed integer). Stereo is downmixed to mono.
"""

from __future__ import annotations

import argparse
import array
import asyncio
import datetime as dt
import logging
import os
import sys
import wave

from dotenv import load_dotenv
from livekit import rtc
from livekit.api import AccessToken, VideoGrants

logger = logging.getLogger("publish_wav")

FRAME_MS = 20  # 20ms per AudioFrame is a common WebRTC chunk size


def _read_wav(path: str) -> tuple[bytes, int, int]:
    """Return (pcm_bytes, sample_rate, num_channels) — coerced to int16 mono."""
    with wave.open(path, "rb") as wf:
        sample_rate = wf.getframerate()
        num_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if sample_width != 2:
        raise SystemExit(f"WAV must be 16-bit PCM; got {sample_width * 8}-bit")

    if num_channels == 1:
        return frames, sample_rate, 1

    if num_channels == 2:
        # Downmix to mono by averaging the two channels.
        samples = array.array("h")
        samples.frombytes(frames)
        mono = array.array("h", (
            (samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)
        ))
        return mono.tobytes(), sample_rate, 1

    raise SystemExit(f"Unsupported channel count: {num_channels}")


def mint_token(api_key: str, api_secret: str, room: str, identity: str) -> str:
    grants = VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True)
    return (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_name(identity.capitalize())
        .with_grants(grants)
        .with_ttl(dt.timedelta(hours=1))
        .to_jwt()
    )


async def run(url: str, token: str, wav_path: str, identity: str) -> None:
    pcm, sample_rate, num_channels = _read_wav(wav_path)
    samples_per_frame = sample_rate * FRAME_MS // 1000
    bytes_per_frame = samples_per_frame * num_channels * 2  # int16
    total_duration = len(pcm) / (sample_rate * num_channels * 2)
    logger.info(
        "loaded %s: %.2fs, %dHz, %dch (%d frames of %dms)",
        wav_path,
        total_duration,
        sample_rate,
        num_channels,
        len(pcm) // bytes_per_frame,
        FRAME_MS,
    )

    room = rtc.Room()
    await room.connect(url, token)
    logger.info("connected as %s", identity)

    source = rtc.AudioSource(sample_rate, num_channels)
    track = rtc.LocalAudioTrack.create_audio_track(f"mic-{identity}", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await room.local_participant.publish_track(track, options)
    logger.info("published track; streaming %s in real time…", wav_path)

    # Capture frames at real-time pace. capture_frame awaits when the internal queue fills,
    # so this naturally throttles to 1x playback speed.
    for offset in range(0, len(pcm) - bytes_per_frame + 1, bytes_per_frame):
        frame = rtc.AudioFrame(
            data=pcm[offset : offset + bytes_per_frame],
            sample_rate=sample_rate,
            num_channels=num_channels,
            samples_per_channel=samples_per_frame,
        )
        await source.capture_frame(frame)

    # Allow the last buffered frames to play out.
    await asyncio.sleep(FRAME_MS / 1000 * 5)
    logger.info("done — disconnecting")
    await room.disconnect()


def main() -> int:
    load_dotenv(".env.local")
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", required=True, choices=("doctor", "patient"))
    parser.add_argument("--room", required=True)
    parser.add_argument("--wav", required=True, help="Path to a 16-bit PCM WAV file (mono or stereo)")
    args = parser.parse_args()

    url = os.environ.get("LIVEKIT_URL")
    api_key = os.environ.get("LIVEKIT_API_KEY")
    api_secret = os.environ.get("LIVEKIT_API_SECRET")
    if not (url and api_key and api_secret):
        print("Missing LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET. Run `lk app env -w .` first.", file=sys.stderr)
        return 1
    if not os.path.exists(args.wav):
        print(f"WAV not found: {args.wav}", file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    token = mint_token(api_key, api_secret, args.room, args.identity)
    asyncio.run(run(url, token, args.wav, args.identity))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
