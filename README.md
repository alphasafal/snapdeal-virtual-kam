# Virtual KAM: a voice agent that owns a seller's sales problem

Built for the Snapdeal AI First Intern assignment. A seller talks to "Asha", an AI Key Account
Manager, in the browser. Asha has already studied the account, explains why sales dropped,
asks only what the data cannot tell her, takes actions when the seller agrees, books a
follow-up, and remembers all of it on the next call.

Everything runs on mock data. Seller S1 is the exact table from the assignment brief.

[![tests](https://github.com/alphasafal/snapdeal-virtual-kam/actions/workflows/tests.yml/badge.svg)](https://github.com/alphasafal/snapdeal-virtual-kam/actions/workflows/tests.yml)

<!-- DEMO VIDEO: replace this comment with a line such as   **Demo video (2 min):** https://...   -->

## At a glance

| | |
|---|---|
| **Voice** | Real-time streaming audio over WebRTC, not record-and-wait. The seller can interrupt Asha mid-sentence. English, Hindi and Hinglish, using speech models built for Indian accents. |
| **Diagnosis** | Plain Python splits the ₹65,000 drop into causes: ₹45,450 from stockouts (measured), ₹19,550 from lost visibility (inferred, and labelled as such). The language model never calculates. |
| **Ownership** | Asha saves actions during the call, books a follow-up, and opens the next call with what was agreed. A nightly scan ranks all twelve sellers by the rupees that could be won back, so she calls the right ones first. |
| **Planning** | A what-if planner for every seller: tick the actions they can take and see next month's sales. It quotes the same figures Asha says on the call, and a test checks that. |
| **Trust** | An action is saved only if the seller's own words were a clear yes. After every call each rupee figure she spoke is checked against the data. A person can review and sign off any call. |
| **Evidence** | 134 automated tests, including the real agent run against a scripted model. Twelve sellers across four situations (stockouts, rival pricing, late dispatch, and one that is growing), plus a form to enter any numbers. |

## What it looks like

The call screen after a call: the conversation, what was agreed, and what Asha found before she spoke.

![Call screen](docs/screenshots/call.png)

The team dashboard: a call queue ranked by the sales that could be won back, then every call with its review status.

![Team dashboard](docs/screenshots/dashboard.png)

The what-if planner for one seller.

![What-if planner](docs/screenshots/planner.png)

One call's full record, with the automatic figure check and human review.

![Call record](docs/screenshots/call-record.png)

These screens were captured with the scripted call simulator (`agent/simulate_call.py`), which
needs no keys or microphone.

## How it fits together

```mermaid
flowchart LR
  seller["Seller's browser<br/>(call screen)"]
  room["LiveKit room<br/>(WebRTC audio)"]
  agent["Agent worker<br/>(Python)"]
  stt["Sarvam Saaras<br/>speech-to-text"]
  llm["Sarvam 105B<br/>language model"]
  tts["Sarvam Bulbul<br/>text-to-speech"]
  brain["Brain, plain Python:<br/>diagnosis, playbook,<br/>consent check, figure check"]
  db[("Postgres")]
  web["Next.js web app<br/>(call screen, dashboard, review)"]

  seller <-->|audio| room
  room <-->|audio| agent
  agent --> stt
  agent --> llm
  agent --> tts
  agent --> brain
  brain <--> db
  web <--> db
  seller --- web
```

The agent and the web app never call each other: both read and write the database, so calls
are independent and more agent workers can be added without changing anything else.

**`docs/LIVE_CALL_TEST.md`** is the record of a full call against the real services, with what
was checked, what it found and the whole conversation.

**`docs/ARCHITECTURE.md`** has the full design: a step-by-step call diagram, why each part was
chosen and what it costs, the data model, how it grows to one lakh sellers, and what happens
when each part fails.

## What is in here

New to the code? Read **`docs/CODE_TOUR.md`** first. It explains every file in one line,
follows one call through the code, and lists the words used.

| Folder | What it is |
|---|---|
| `agent/agent.py` | The voice agent (LiveKit Agents), in five labelled parts. |
| `agent/brain/` | Diagnosis engine, tools, what-if planner, consent check, figure check, database layer, mock data. Plain Python, no LLM. |
| `agent/prompts.py` | The agent's instructions. |
| `agent/speech_filter.py` | Keeps any leaked model reasoning out of what is spoken. |
| `agent/tests/` | 134 tests, including the real agent run in a text-only session with a scripted LLM. |
| `web/` | Next.js app: call screen, "try your own numbers", team dashboard with the call queue, what-if planner, call records and human review, how-it-works page. |
| `docs/` | Architecture, code tour, submission note, recording script, deploy guide. |

## Accounts you need (all have free tiers)

1. **Sarvam** – speech-to-text, LLM and text-to-speech. One key.
2. **LiveKit Cloud** – carries the audio. Create a project, copy URL, API key and secret.
3. **Neon** (or any Postgres) – copy the connection string.
4. Optional: **Google AI Studio** key if you want to try `VOICE_MODE=gemini`.

## Run it locally

Quickest: `./start.sh` from the project root does all of the steps below and runs the built web app (`--reset` also wipes call history, `--dev` uses hot-reload mode).

```bash
# 1. Agent
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in the keys (skip if .env already exists)
python hello_sarvam.py        # first Sarvam call: writes hello_sarvam.wav
python -m pytest -q           # 134 tests, no keys needed
python -m brain.seed          # creates tables and the twelve mock sellers (wipes calls)
python agent.py console       # optional: talk to Asha in the terminal
python agent.py dev           # leave this running; it waits for calls

# 2. Web app (second terminal)
cd web
cp .env.example .env.local    # same DATABASE_URL and LiveKit keys
npm install
npm run dev                   # open http://localhost:3000
```

No microphone or keys handy? `python simulate_call.py` plays a scripted call into the database
so you can see the transcript, action panel, summary and dashboard working.

## Deploy

See `docs/DEPLOY.md` for a public link (hosted database, agent on LiveKit Cloud, web app on Vercel).
For a recording, the agent on your laptop is enough.

## Voice settings

| Setting (in `agent/.env`) | Default | What it does |
|---|---|---|
| `VOICE_MODE` | `sarvam` | Default voice: `sarvam` pipeline or `gemini` (Gemini Live). The call screen can also choose per call. |
| `GOOGLE_API_KEY` | unset | Needed for Gemini Live. If the key or model is unavailable the call falls back to Sarvam. `python hello_gemini.py` checks it. |
| `SARVAM_STT_TRANSPORT` | `auto` | `auto` = live websocket with per-sentence HTTPS as fallback; `http` or `ws` forces one |
| `SARVAM_TTS_MODEL` | unset | unset = Bulbul v4 Flash first, Bulbul v3 as fallback; set a model name to force it |
| `SARVAM_REASONING_EFFORT` | `none` | model "thinking" is off: it made replies slow and leaked into speech |
| `LLM_TIMEOUT_S` | `4` | seconds of silence from the language model before the request is retried |
| `ENDPOINT_MAX_DELAY` | `1.6` | longest wait (seconds) before deciding the seller has finished; raise it if sellers get cut off mid-thought |

## Safeguards that do not rely on the model behaving

| Safeguard | Where | What it does |
|---|---|---|
| Consent gate | `agent/brain/consent.py` | An action is saved only if the seller's own last words clearly agreed to that specific action. A question, or a yes to a different question, does not count. One yes covers at most two actions. |
| Undo | `cancel_action` tool | If the seller says they did not want something, it is removed and its effects are reversed. |
| Figure check | `agent/brain/audit.py` | After every call, each rupee amount the agent spoke (English, Hindi, Hinglish) is compared with the account data and tool results. Anything unmatched is flagged on the call record. |
| Reasoning filter | `agent/speech_filter.py` | Leaked model reasoning never reaches the voice or the transcript. |
| Playbook | `KamTools.playbook()` | Code decides which actions fit this seller, biggest problem first. |

These came from real test calls: a model acted without consent, invented an answer, and said
"6 lakh" for 2 lakh. On a live Hindi call the consent gate itself was too strict: it refused
"कर दीजिए।" because speech-to-text ends sentences with "।", and it refused a "ठीक है" that came
back in Gurmukhi script. Each failure is now a test case.

## Human review

Every finished call has its own page (Team dashboard, then "Open call") with the summary, every
action, the full conversation including what the agent looked up, and what the seller said.
A team member can mark the call as reviewed or flag it for follow-up, with a note.

## Reliability choices

- One worker process is kept warm and its database connection is kept open, so that work is not
  done while the seller waits. `agent.log` prints how long each call took to set up.
- A language-model request that sends nothing for four seconds is abandoned and retried at once
  (`LLM_TIMEOUT_S`). On a live call, waiting the default ten seconds twice gave a 25-second silence.
- Asha's goodbye cannot be interrupted, so a background noise cannot cut the call off mid-sentence.
- No microphone? The call still connects in typing mode: the seller types, Asha answers aloud, and
  every tool, consent check and record works the same way.
- `GET /api/health` on the web app answers 200 only when the database is reachable.

- Transcription and voice each have a fallback, and the call survives up to 12 provider errors.
- If the call does drop, the page says so and the next call picks up from what was agreed.
- The call record is written the moment the conversation ends.
- `MAX_CALLS_PER_HOUR` (web, default 60) caps spend on a public demo link.

## What is real and what is mocked

Real: the voice conversation, the diagnosis arithmetic, tool calls, saved actions, call memory,
the dashboard, cost and response-time tracking.

Mocked: all seller data; the effect of actions (a restock plan is a saved record, not a purchase
order; "paused" and "repriced" only change the mock product table); the WhatsApp summary is not sent.
