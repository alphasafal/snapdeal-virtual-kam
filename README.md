# Virtual KAM: a voice agent that owns a seller's sales problem

Built for the Snapdeal AI First Intern assignment. A seller talks to "Asha", an AI Key Account
Manager, in the browser. Asha has already studied the account, explains why sales dropped,
asks only what the data cannot tell her, takes actions when the seller agrees, books a
follow-up, and remembers all of it on the next call.

Everything runs on mock data. Seller S1 is the exact table from the assignment brief.

## What is in here

New to the code? Read **`docs/CODE_TOUR.md`** first. It explains every file in one line,
follows one call through the code, and lists the words used.

| Folder | What it is |
|---|---|
| `agent/agent.py` | The voice agent (LiveKit Agents), in five labelled parts. |
| `agent/brain/` | Diagnosis engine, tools, consent check, figure check, database layer, mock data. Plain Python, no LLM. |
| `agent/prompts.py` | The agent's instructions. |
| `agent/speech_filter.py` | Keeps any leaked model reasoning out of what is spoken. |
| `agent/tests/` | 117 tests, including the real agent run in a text-only session with a scripted LLM. |
| `web/` | Next.js app: call screen, "try your own numbers", team dashboard with call records and human review, how-it-works page. |
| `docs/` | Code tour, submission note, recording script, deploy guide. |

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
python -m pytest -q           # 117 tests, no keys needed
python -m brain.seed          # creates tables and the three mock sellers (wipes calls)
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

- Transcription and voice each have a fallback, and the call survives up to 12 provider errors.
- If the call does drop, the page says so and the next call picks up from what was agreed.
- The call record is written the moment the conversation ends.
- `MAX_CALLS_PER_HOUR` (web, default 60) caps spend on a public demo link.

## What is real and what is mocked

Real: the voice conversation, the diagnosis arithmetic, tool calls, saved actions, call memory,
the dashboard, cost and response-time tracking.

Mocked: all seller data; the effect of actions (a restock plan is a saved record, not a purchase
order; "paused" and "repriced" only change the mock product table); the WhatsApp summary is not sent.
