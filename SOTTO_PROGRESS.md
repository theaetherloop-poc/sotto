# Sotto — Progress & Handoff

> Resume doc for the Sotto ambient voice-agent build. Last updated: 2026-06-06.

## What Sotto is

An **ambient AI co-pilot** for a functional-medicine consult. It joins a LiveKit room with two
humans (**doctor** + **patient**), listens to both mics, transcribes them in real time, and pushes
concise **context cards** to the doctor's screen — *Suggested Next Question*, *Patient Context*,
*Protocol Direction* — only when there's a clear opportunity. The agent never speaks; output is
text cards. Hackathon entry for the Co-Pilot track.

## Current status: WORKING (pending final live confirmation)

- **Agent (CLI + backend): working.** Joins room, subscribes to both tracks, Deepgram STT per
  speaker, merged transcript, LLM cue engine emits cards to stdout + a jsonl file + a data channel.
- **Frontend dashboard: built, all known bugs fixed.** Doctor view publishes mic + shows live cue
  cards + a patient share link; patient joins via meet.livekit.io.
- **Tests:** 28 agent unit tests passing (`pnpm test:sotto`). Frontend typechecks + lints clean.
- **Last open item:** a live two-mic browser run to confirm cards render end-to-end and the call
  stays connected after the final fix (removing the agent-failure watchdog). Could not be verified
  headlessly (needs a real mic at each end).

## Architecture

```
  doctor (mic, identity "doctor-xxxx") ─┐                  ┌─ localhost:3000 doctor dashboard
  patient (mic, identity "patient-xxx")─┤  WebRTC          │   (mic + live cue cards + share link)
                                        ▼                  │
                              LiveKit Cloud room ──────────┘
                                        │ auto-dispatch (agent has no agent_name)
                                        ▼
                       sotto-agent (Python, AgentServer + @server.rtc_session)
                         on track_subscribed → per-speaker Deepgram STT (streaming)
                         → MergedTranscript (chronological, speaker-labeled)
                         → 500ms debounce → CueEngine (gpt-4.1-mini)
                         → cue card → 3 sinks:
                              • stdout (rich panel)
                              • logs/sotto-cues.jsonl
                              • LiveKit data channel, topic "sotto_cue", {type,data} envelope
                                        │
                                        ▼
                       frontend useSottoCues hook → SottoCuePanel (doctor only)
```

- **Not** an `AgentSession` 1:1 voice agent — it's a raw room worker with manual track subscription.
- All AI runs through **LiveKit Inference** (no separate provider API keys).

## Repo layout

Monorepo: `/Users/tusharm/Downloads/Livekit-2/moss-hacker-starter/`
(There is also an original copy at `/Users/tusharm/Downloads/Livekit-2/sotto-agent/` — the canonical
one is now inside the monorepo; the top-level copy can be deleted.)

```
moss-hacker-starter/
├── sotto-agent/                      # THE Sotto Python agent (uv project)
│   ├── src/sotto_agent.py            # entrypoint: AgentServer, track subscription, STT wiring, sinks
│   ├── src/sotto/
│   │   ├── transcript.py             # MergedTranscript + TranscriptFileWriter
│   │   ├── cue_engine.py             # CueEngine + SYSTEM_PROMPT + JSON parsing
│   │   ├── sinks.py                  # Card, StdoutSink, DataChannelSink, JsonlSink
│   │   └── scripts/
│   │       ├── gen_tokens.py         # print doctor/patient meet.livekit.io join URLs
│   │       └── publish_wav.py        # publish a wav as a participant's mic (scripted scenarios)
│   ├── tests/                        # 28 tests (transcript, cue engine, sinks, speaker_for)
│   ├── logs/                         # sotto-cues.jsonl + sotto-transcript.jsonl (gitignored)
│   └── .env.local                    # LIVEKIT_URL / KEY / SECRET (project: yc-hackathon)
├── frontend/                         # Next.js dashboard (adapted from agent-starter-react)
│   ├── app/api/token/route.ts        # mints role-based unique identities (doctor-xxx/patient-xxx)
│   ├── components/app/app.tsx        # role/room from URL, token source, patient meet URL, disconnect logger
│   ├── components/app/view-controller.tsx        # threads role + patientShareUrl
│   ├── components/app/sotto-cue-panel.tsx         # the cue card UI (3 types, color-coded)
│   ├── components/app/patient-share-link.tsx      # copyable patient join link
│   ├── hooks/useSottoCues.ts         # subscribes to "sotto_cue" data topic
│   ├── lib/utils.ts                  # getSottoTokenSource + fetchPatientMeetUrl
│   ├── components/.../agent-session-block.tsx     # renders cue rail (doctor only)
│   └── next.config.ts                # reactStrictMode: false (see bug #4)
├── package.json                      # root scripts incl. dev:sotto, sotto, sotto:tokens, test:sotto
└── SOTTO_PROGRESS.md                 # this file
```

## Models configured (all via LiveKit Inference)

| Layer | Value | Location |
|---|---|---|
| STT | `deepgram/nova-3`, lang `en`, streaming, one per speaker | `sotto_agent.py:31` |
| LLM (cue engine) | `openai/gpt-4.1-mini`, temp 0.2 | `sotto_agent.py:33` |
| VAD / TTS / turn-detection | **none** (ambient listener, never speaks) | — |

No FallbackAdapter chains (single models, by choice). Easy to add later.

## Prompts (all agent-side, one file)

- **System prompt:** `sotto-agent/src/sotto/cue_engine.py:21-53` (`SYSTEM_PROMPT`). Defines role,
  JSON output contract, the 3 card types, and rules ("bias HARD toward none", "output only JSON").
  **Edit here to change behavior.** Currently biased strongly toward silence.
- **Per-turn user message:** `cue_engine.py:126-129` (f-string: recent cards + last 30s transcript).
- **Wired in:** `sotto_agent.py:55` via `chat_ctx.add_message(role="system", content=SYSTEM_PROMPT)`.
- No prompts in the frontend. No STT prompt (Deepgram runs without one).

## How to run

Prereqs already set up: `uv`, `pnpm` (via corepack), `lk` CLI authed to project `yc-hackathon`.
Frontend deps installed; both `.env.local` files have LIVEKIT_URL/KEY/SECRET on the same project.

From `moss-hacker-starter/`:
```bash
# Two terminals:
pnpm dev:sotto       # the ambient agent (auto-dispatches to new rooms)
pnpm dev:frontend    # Next.js on http://localhost:3000
# (or `pnpm sotto` to run both together)
```
1. Open http://localhost:3000 → "Start call" → you join as `doctor`, see the cue rail + patient link.
2. Copy the **patient link** (a meet.livekit.io URL) → open on a phone/another device → "Start".
3. Talk through symptoms. Cards stream into the doctor dashboard.

CLI-only smoke test (no frontend): `pnpm sotto:tokens --room sotto-test` → prints two
meet.livekit.io URLs; or `uv --directory sotto-agent run src/sotto_agent.py console`.

Logs (from `sotto-agent/`): `tail -f logs/sotto-transcript.jsonl` and `logs/sotto-cues.jsonl`.
Run tests: `pnpm test:sotto`.

## Bugs fixed during the build (root causes — important context)

1. **LLM `response_format` crash.** `livekit-agents 1.5.17`'s `to_response_format_param` raises on
   the OpenAI-style `{"type":"json_object"}` dict (only accepts a Pydantic model). Fix: removed
   `response_format`; rely on the system prompt + a tolerant JSON parser (`_extract_json` handles
   code fences / surrounding prose). `sotto_agent.py` + `cue_engine.py`.
2. **Stale-room / dispatch.** Reusing a room name across runs blocks auto-dispatch (agent only
   dispatches to rooms created *after* it's listening). Frontend now generates a fresh room per load.
3. **Patient link used localhost.** Useless across devices + mic blocked on non-localhost http.
   Fix: patient link is now a **meet.livekit.io** URL with a minted patient token
   (`fetchPatientMeetUrl` in `lib/utils.ts`).
4. **Duplicate-identity kick.** Fixed identity `"doctor"` + React StrictMode double-mount → LiveKit
   evicts the duplicate. Fix: unique identities `doctor-xxxxxx`; agent derives role from the prefix
   (`speaker_for()` in `sotto_agent.py`). Also set `reactStrictMode: false` (`next.config.ts`)
   because `useSession` connects/disconnects the room directly and isn't StrictMode-safe.
5. **Drops mid-conversation (THE big one).** `useAgentErrors` is a watchdog for *conversational*
   voice agents — when `agent.state === 'failed'` (agent never reaches a speaking/listening state
   within the connect timeout) it force-calls `end()` → disconnect. Sotto is ambient and never
   reports a conversational state, so it always tripped. Fix: removed `useAgentErrors()` from
   `app.tsx`. Added a plain-text disconnect-reason logger (`[SOTTO] room disconnected — reason:`).

## Known limitations / residual risks

- **Reconnect after a drop:** `useSession` refetches a token for the *same* room on disconnect, but
  agents won't rejoin a previously-existing room. If a call drops (network blip), restart it. A
  fresh-room-on-reconnect path is not yet implemented.
- **Same-room mic crosstalk:** if doctor & patient are in the same physical room, both mics may pick
  up both voices, muddying speaker attribution. Out of scope for Phase 1.
- **`patient_context` cards are invented** by the LLM (Phase 1). Real labs/wearables come in Phase 2.
- **Token route is dev-only** (`throws in production`) — needs real auth before any deploy.
- **Two pnpm lockfiles** trigger a Next "inferred workspace root" warning (harmless).

## Next steps (Phase 2+)

1. **Moss RAG integration** — replace invented `patient_context` with real retrieval over the Moss
   `knowledge` index; the moss-hacker-starter already has the Moss agent + indexer to borrow from.
2. **Real patient data** — labs / wearables / EHR adapters feeding `patient_context`.
3. **Prompt tuning** — the cue engine is biased hard toward silence; may want it more eager. Single
   file: `cue_engine.py` `SYSTEM_PROMPT`.
4. **Transcript panel in the UI** (currently transcript is stdout + jsonl only).
5. **Model resilience** — add FallbackAdapter chains for STT/LLM if desired.
6. **Deploy** — agent via `lk agent create` from `sotto-agent/`; secure the token route first.

## Key facts for a new chat

- LiveKit project: `yc-hackathon` (`wss://yc-hackathon-4ljxd2jk.livekit.cloud`).
- LiveKit docs MCP is configured (`.mcp.json` at `/Users/tusharm/Downloads/Livekit-2/`) — use it to
  verify LiveKit APIs (never trust model memory; the SDK evolves fast).
- The `livekit-agents` Claude skill lives at
  `moss-hacker-starter/sotto-agent/.claude/skills/livekit-agents` and mandates tests.
- Original plan doc: `/Users/tusharm/.claude/plans/sotto-an-ambient-hashed-volcano.md`.
