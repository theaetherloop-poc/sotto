**How to use?**
1. Got to the hosted app and initiate a call.
2. You will go to the doctor view. As a doctor, share the link with another user who will be the patient in the this coversation.
3. 2 users (Doctor and Patient) need to log in from two different devices.Ideal environment for conversation is a quiet room and use headphones
4. Once both users are logged in and connected, use the Sotto_Capture_LiveScript.docx to have a sample conversatoin. This tests three core value adds in the solution
   
  **Ambient Co-pilot- Live Root-cause probe**
    
    Patient: “I used to work at a print shop, lots of solvents.”.
    
    Within 2s a Suggested Next Question stack appears — 
    solvent names? route (inhaled / skin)? duration? PPE? symptoms? — each cited to the KB. 
    
    Practitioner reads one aloud.

     
   **“That’s our functional-medicine question library, retrieved live by the retrieval engine.”**
  
**Moss orchestration with KB,Wearables and EHR integration — Fused context**

   Patient: “I’ve just been so exhausted lately.” 
   
   → Patient Context card: “Oura: avg 5.5h sleep, HRV ↓20% over 3 weeks” + “Ferritin trending down, last 2 panels (EHR).” 
   
   
**“Three data sources fused in under two seconds.”**
 
**- Novel Functional Medicine AI usage - Protocol direction -**

  Copilot surfaces a Protocol Direction card (when Generate Protocol is clicked) from the recommendation engine, with citations. 
  
**“Grounded in the patient’s own data — not a hallucination.”**

YOU CAN CHOOSE TEST WITHOUT THE SCRIPT TOO. THE SCRIPT ALLOWS TESTING ALL THE FEATURES.
5. Leave the call once finished.



# Sotto — ambient AI co-pilot for live functional-medicine consults

> *Sotto voce* — "in a low voice."
> Sotto listens to a doctor-patient consultation in real time and quietly surfaces context
> cards to the doctor's screen — never speaks, never interrupts.

It joins a [LiveKit](https://livekit.io) room with two humans (**doctor** + **patient**),
transcribes each microphone via Deepgram Nova-3 Medical, feeds a merged speaker-labeled
transcript into an LLM cue engine (GPT-5 mini), and pushes one of three card types to the
doctor's dashboard when the model judges there's a clear opportunity:

- **Suggested Next Question** — a root-cause follow-up worth asking now.
- **Patient Context** — a relevant fact (labs, wearables, history; Phase 1 invents plausibly).
- **Protocol Direction** — a directional intervention worth exploring.

**This is a hackathon POC, not a production system.** It does not handle PHI, has no
authentication, and is intended for demos and internal exploration only.

<img width="682" height="710" alt="architecture png" src="https://github.com/user-attachments/assets/a8c61f57-0876-4bf4-9fbd-3ef92b90ccf0" />

<img width="1526" height="868" alt="image (7)" src="https://github.com/user-attachments/assets/c2659129-67fc-499c-9046-bebb581f5fee" />



## Repository layout

```
.
├── sotto-agent/       # Python agent (uv project) — joins rooms, runs STT + cue engine
│   ├── src/sotto_agent.py       # entrypoint: AgentServer + rtc_session
│   ├── src/sotto/               # cue_engine, transcript, sinks, metrics, telemetry
│   ├── Dockerfile               # for `lk agent deploy` to LiveKit Cloud
│   └── tests/                   # 40 unit tests
├── frontend/          # Next.js 15 dashboard (doctor + patient views)
├── agent-py/          # original Moss starter agent (unused by Sotto, kept for reference)
├── vercel.json        # tells Vercel the frontend lives in /frontend
└── README.md
```

## Architecture

```
  doctor (mic, identity "doctor-xxxxxx") ─┐                  ┌─ Vercel: Next.js doctor dashboard
  patient (mic, identity "patient-xxxxxx")┤  WebRTC          │   (mic + live cue cards + share link)
                                          ▼                  │
                                LiveKit Cloud room ──────────┘
                                          │ auto-dispatch (sotto-agent has no agent_name)
                                          ▼
                         LiveKit Cloud (agent): sotto-agent
                           on track_subscribed → per-speaker Deepgram STT (streaming)
                           → MergedTranscript (chronological, speaker-labeled)
                           → 500ms debounce → CueEngine (gpt-5-mini, reasoning_effort=low)
                           → cue card → 2 sinks: stdout + LiveKit data channel
                                          │
                                          ▼
                         frontend useSottoCues hook → SottoCuePanel (doctor only)
```

- **Not** an `AgentSession` 1:1 voice agent. It's a raw `@server.rtc_session` worker with
  manual track subscription, because Sotto never speaks.
- All AI runs through **LiveKit Inference** — no separate STT/LLM API keys.

## Models in use

| Layer | Value | Why |
|---|---|---|
| STT | `deepgram/nova-3-medical` | English; medical vocabulary tuned for drugs / anatomy / labs |
| LLM (cue engine) | `openai/gpt-5-mini` (`reasoning_effort=low`) | Reasoning model; strong judgment on the "emit or stay silent" call |
| VAD / TTS / turn-detection | none | Sotto never speaks |

## Local development

Prereqs: [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) authed to a LiveKit Cloud project.

```bash
# 1. Copy env templates and fill in LIVEKIT_URL / KEY / SECRET (same values in both files).
cp sotto-agent/.env.example sotto-agent/.env.local
cp frontend/.env.example frontend/.env.local

# 2. Install deps.
pnpm install --dir frontend
uv --directory sotto-agent sync

# 3. Run both processes concurrently (or split into two terminals).
pnpm sotto     # = pnpm dev:sotto + pnpm dev:frontend

# 4. Open http://localhost:3000 → "Start call" → join as doctor.
#    Copy the patient share link (meet.livekit.io) to a phone/another device.
```

Useful scripts:

```bash
pnpm test:sotto                      # 40 backend tests
pnpm sotto:tokens --room sotto-test  # mint doctor/patient meet.livekit.io URLs for CLI testing
```

## Deployment

The dashboard runs on Vercel; the agent runs on LiveKit Cloud. They communicate through your
LiveKit project — no direct connection between the two hosts.

### 1. Deploy the agent to LiveKit Cloud

```bash
cd sotto-agent
lk cloud auth                  # if not already authed
lk agent create                # builds Dockerfile, deploys, writes livekit.toml with the agent ID
```

The CLI uploads the build context (which excludes `.env.*` per `.dockerignore`), builds an
image, and starts the worker. The agent registers with no `agent_name`, so LiveKit
auto-dispatches it to every new room in the project.

On subsequent deploys, run `lk agent deploy` from the same directory.

### 2. Deploy the dashboard to Vercel

From the repo root:

1. Import the GitHub repo at [vercel.com/new](https://vercel.com/new).
2. **Set the Root Directory to `frontend`** — `vercel.json` at the repo root already pins
   the framework, build, and install commands.
3. Add these environment variables under Project Settings → Environment Variables:
   - `LIVEKIT_URL` — `wss://<your-project>.livekit.cloud`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
4. Deploy.

Once both halves are live, opening the Vercel URL spins up a doctor session that the
deployed agent will auto-join.

## Environment variables

### `frontend/.env.local`

| Key | Required | Notes |
|---|---|---|
| `LIVEKIT_URL` | yes | `wss://…` from your LiveKit Cloud project |
| `LIVEKIT_API_KEY` | yes | LiveKit API key |
| `LIVEKIT_API_SECRET` | yes | LiveKit API secret |

### `sotto-agent/.env.local` (local dev only)

Same three keys as above. In LiveKit Cloud, `LIVEKIT_URL` / `KEY` / `SECRET` are injected at
runtime — **never** copy them into the Dockerfile or commit them.

### Optional: OpenTelemetry export

Set one of these groups to stream agent spans to your observability backend:

| Backend | Vars |
|---|---|
| LangFuse | `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` |
| Generic OTLP/HTTP (Honeycomb, Datadog, etc.) | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS` |

When set, install the extras: `uv --directory sotto-agent sync --extra telemetry`. When
unset, tracing is a no-op.

## Observability

Two surfaces, both backend-only (no production UI panel by design):

| Surface | Path |
|---|---|
| **Per-session summary** (one line per call) | `sotto-agent/logs/sotto-sessions.jsonl` |
| **Per-event metrics** (every STT / LLM / eval) | `sotto-agent/logs/sotto-metrics.jsonl` |
| Cue cards (existing) | `sotto-agent/logs/sotto-cues.jsonl` |
| Final transcripts (existing) | `sotto-agent/logs/sotto-transcript.jsonl` |
| LiveKit Cloud → Agent insights | `cloud.livekit.io` → project → Sessions tab |
| Optional OTel backend | LangFuse / Datadog / Honeycomb (see env vars above) |

The session summary is written through a `ctx.add_shutdown_callback`, so it appears
regardless of how the session ends (clean disconnect, exception, process kill).

## Important caveats

- **Open token route.** `frontend/app/api/token/route.ts` mints LiveKit tokens with no
  authentication. Any traffic to the deployed Vercel URL consumes your LiveKit Inference
  credits. Gate it before broadening access.
- **No PHI handling.** This is a demo. Do not run real patient sessions through it without
  HIPAA controls (BAA with LiveKit on the Scale plan, encrypted log storage, real auth,
  audit logging).
- **`patient_context` cards are invented** by the LLM in Phase 1. Real labs and wearable
  data integration is a planned Phase 2 (using the Moss RAG infrastructure in `agent-py/`).
- **Reconnect-after-drop** isn't implemented. If a session drops mid-call, restart it.

## Tests

```bash
pnpm test:sotto
```

40 tests covering: speaker mapping, transcript merging, sinks, cue engine (debounce,
in-flight lock, parse, dedup, metrics), metrics aggregation, and the telemetry no-op path.
