# Code tour

Read this first if you are new to the code. It takes about ten minutes, and after it
every file should make sense when you open it. For the design decisions behind it, how it
scales and how it fails, read `ARCHITECTURE.md`.

## The idea in four sentences

A seller talks to "Asha", an AI account manager, in the browser.
Before she speaks, plain Python code works out why the seller's sales fell and which
actions would help.
A language model does the talking and decides when to use a tool, but code computes every
number, checks the seller really said yes before anything is saved, and checks afterwards
that every figure she spoke was true.
Everything is stored in one database, which is also how the web pages know what happened.

## The two halves

| Half | Folder | Language | Job |
|---|---|---|---|
| Voice agent | `agent/` | Python | Listens, speaks, diagnoses, acts, records |
| Web app | `web/` | TypeScript (Next.js) | Call screen, team dashboard, call records |

They never call each other directly. The web app creates a call row in the database and a
LiveKit room; the agent joins that room and writes what happens back to the database; the
web app reads it once a second.

## Every file, one line each

### `agent/`

| File | What it is |
|---|---|
| `agent.py` | The voice agent. Five labelled parts: settings, the agent and its tools, voice set-up, call recording, the worker. Start with the comment at the top. |
| `prompts.py` | Asha's instructions (the system prompt) and how they are assembled for one call. |
| `speech_filter.py` | Removes a model's leaked "thinking" from a reply before it is spoken. |
| `brain/diagnosis.py` | **The diagnosis engine.** Pure arithmetic with a worked example at the top. Read this one carefully. |
| `brain/tools.py` | Everything Asha can look up or do: restock plan, pause listings, price match, follow-up, undo, the playbook, the summary. |
| `brain/consent.py` | Decides whether the seller's words were a clear yes to a specific action. |
| `brain/audit.py` | After a call, finds every rupee amount Asha spoke and checks it against the data. |
| `brain/repo.py` | All database reads and writes, in five labelled sections. |
| `brain/db.py` | The database tables, listed and described at the top. |
| `brain/seed.py` | The twelve mock sellers. Seller S1 is the table from the assignment brief; S1 to S3 are the detailed ones used in the demo. |
| `brain/planner.py` | The what-if planner: the actions open to a seller and the rupees each could win back. |
| `brain/jobs.py` | The nightly scan: diagnoses every seller and stores the planner's options, which is what ranks the call queue. |
| `simulate_call.py` | Plays a scripted call into the database with no audio, to check the screens. |
| `hello_sarvam.py`, `hello_gemini.py` | One-file checks that each API key works. |
| `tests/` | 138 tests. `test_agent_session.py` runs the real agent with a scripted model. |

### `web/`

| File | What it is |
|---|---|
| `components/CallScreen.tsx` | The live call screen; the only file that touches audio. Explained at the top. |
| `app/page.tsx` | Home: pick a seller or enter your own numbers. |
| `app/seller/[id]/page.tsx` | One seller: loads their data, then hands over to `CallScreen`. |
| `app/dashboard/page.tsx` | Team dashboard: the call queue ranked by recoverable sales, then calls and review status. |
| `app/seller/[id]/plan/page.tsx`, `components/Planner.tsx` | The what-if planner page for one seller. |
| `app/dashboard/calls/[id]/page.tsx` | One call's full record with the human review form. |
| `app/how-it-works/page.tsx` | The explanation page for reviewers. |
| `app/api/calls/route.ts` | Creates a call and a LiveKit token. |
| `app/api/calls/[id]/route.ts` | The call's live state, polled by the call screen. |
| `app/api/calls/[id]/review/route.ts` | Saves a human review. |
| `app/api/sellers/route.ts` | Saves a seller typed into the "own numbers" form. |
| `app/api/simulate-week/route.ts` | Demo helper: pretend a week passed. |
| `lib/db.ts`, `lib/format.ts` | Database connection and display helpers. |

## Follow one call through the code

1. The seller clicks **Start call**. `CallScreen.start()` posts to `app/api/calls/route.ts`,
   which inserts a row in `calls` and returns a LiveKit token. The room name is the call id.
2. LiveKit offers the room to the agent worker. `agent.py: accept_only_our_calls()` takes it
   if the call exists in its database.
3. `agent.py: entrypoint()` runs in a process that `prewarm()` already made ready.
   It creates `KamTools` for the seller, which runs `diagnosis.diagnose()` straight away.
4. `KamTools.account_brief()` turns the diagnosis and `KamTools.playbook()` into text.
   `prompts.build_instructions()` puts that text into Asha's instructions.
5. `build_session()` builds the audio pipeline: Sarvam speech-to-text, the Sarvam language
   model, Sarvam text-to-speech. Asha greets the seller.
6. The seller speaks. The model replies, and may call a tool: one of the `@function_tool`
   methods on `KamAgent`.
7. If the tool is an action, `KamAgent._act()` asks `_consent()`, which uses
   `consent.seller_agreed()` on the seller's own last words. No clear yes, no save.
8. `CallRecorder` hears every finished utterance and every tool call and writes them to
   `call_turns`. The call screen shows them within a second.
9. The call ends. `CallRecorder._finish()` rebuilds the summary, runs `audit.audit_call()`
   over everything Asha said, and saves the call with its cost and reply delay.
10. On the dashboard a team member opens the call and marks it reviewed.

## If you read only five things

1. The top comment of `agent/brain/diagnosis.py` (the worked example).
2. `agent/prompts.py` (how Asha is told to behave).
3. `KamAgent._act()` and `_consent()` in `agent/agent.py` (why actions cannot be faked).
4. `KamTools.playbook()` in `agent/brain/tools.py` (how actions are chosen).
5. The top comment of `web/components/CallScreen.tsx`.

## Where each requirement of the brief lives

| The brief asks for | Where |
|---|---|
| Greet the seller and understand the reason for the call | `prompts.py`, CALL FLOW steps 1 and 2 |
| Two-way voice conversation | `agent.py: build_session()`, `web/components/CallScreen.tsx` |
| Relevant follow-up questions | The `question` on each cause in `diagnosis.py`, used by `prompts.py` step 4 |
| Use the sample data to find issues | `brain/seed.py` (seller S1), `brain/diagnosis.py` |
| Recommend 2 to 3 practical actions | `KamTools.playbook()` and the action methods in `brain/tools.py` |
| Summarise at the end | `KamTools.wrap_up()` and `build_summary()` |
| "Take ownership and drive the next action" | Actions saved during the call, `schedule_followup()`, `memory_brief()`, `brain/jobs.py` |

## The safeguards, and the test call behind each

| Safeguard | Code | What went wrong first |
|---|---|---|
| Consent gate | `brain/consent.py`, `KamAgent._act()` | A model saved three actions while the seller was asking a question. |
| Undo | `KamTools.cancel_action()` | The seller said no, and the action stayed on screen. |
| Figure check | `brain/audit.py` | A model said "6 lakh" when the figure was 2 lakh. |
| Playbook | `KamTools.playbook()` | A model offered price cuts to a seller whose pricing was fine. |
| Escalation rules | `KamTools.escalate_to_human()` | A model escalated because the seller said thank you. |
| Reasoning filter | `speech_filter.py` | A model read its private reasoning aloud. |
| Fallbacks and warm start | `build_session()`, `prewarm()`, `keep_database_warm()` | Calls died on a weak network; pick-up was slow. |
| Hindi yes/no matching | `consent.tidy()` | The gate refused "कर दीजिए।" (the Hindi full stop was read as a letter) and a "ठीक है" written in Gurmukhi. |
| Short model time-out | `build_session()` (`llm_retry`) | The model sent nothing for ten seconds, twice: a 25-second silence. |
| Protected goodbye | `KamAgent._protect_goodbye()` | A background noise cut the goodbye off after three words. |
| Three recommendations | `RECOMMENDED_ACTIONS` in `brain/tools.py` | Asha walked through five actions; the brief asks for two or three. |

## Words used in the code

| Word | Meaning |
|---|---|
| KAM | Key Account Manager: the person (here, the agent) who looks after a seller. |
| Brief | The text about one seller given to the model before a call: numbers, diagnosis, playbook. |
| Playbook | The short ordered list of actions that fit this seller. |
| Turn | One thing said on a call, by the seller or by Asha. |
| Tool | A function the language model is allowed to call. |
| Action | A tool that changes something and therefore needs the seller's yes. |
| prev / curr | Last month / this month. |
| asp | Average selling price. |
| oos | Out of stock. |
| STT / TTS | Speech-to-text / text-to-speech. |
| VAD | Voice activity detection: noticing when someone is speaking. |
| Codemix | Speech that mixes Hindi and English. |
| IST | India Standard Time. |

## Running the tests

```bash
cd agent && source .venv/bin/activate && python -m pytest -q
```

They need no microphone and no API keys. `test_diagnosis.py` checks the arithmetic against
the brief, `test_consent.py` and `test_audit.py` include lines from real calls, and
`test_agent_session.py` runs the real `KamAgent` in a text-only session with a scripted model.
