# Sotto — Phase 1 CLI Prototype

An ambient LiveKit agent that joins a consult room, listens to a `doctor` and a `patient`
participant, transcribes both streams via Deepgram (LiveKit Inference), merges them into one
chronological transcript, and emits text-only cue cards to stdout / a data channel / a jsonl log.

The agent does not speak. It is a listener with an LLM-driven cue engine.

## Quickstart

```bash
# 1. Install deps
uv sync

# 2. Populate LiveKit credentials (one-time, uses your linked Cloud project)
lk app env -w .

# 3. Run the agent worker (terminal A)
uv run python src/sotto_agent.py dev

# 4. In another terminal, generate join URLs for the two simulated participants
uv run python -m sotto.scripts.gen_tokens --room sotto-test

#    Open the two printed URLs in two browser tabs at https://meet.livekit.io/
#    Allow mic on both. Speak. The agent terminal shows the merged transcript
#    and any cue cards.
```

## Scripted scenarios with wav files

```bash
# Run in two more terminals, alongside the worker:
uv run python -m sotto.scripts.publish_wav --identity doctor  --room sotto-test --wav fixtures/doctor.wav
uv run python -m sotto.scripts.publish_wav --identity patient --room sotto-test --wav fixtures/patient.wav
```

## Tests

```bash
uv run pytest -v
```

## Phase 1 scope

- Audio in → STT → merged transcript → LLM cue engine → text cards out
- No Moss, no RAG, no React frontend — those come in Phase 2

See `/Users/tusharm/.claude/plans/sotto-an-ambient-hashed-volcano.md` for the full plan.
