"""The voice agent: "Asha", a Virtual Key Account Manager for Snapdeal sellers.

This file connects four things: the seller's audio (through LiveKit), a voice model that
listens and speaks, the instructions in prompts.py, and the "brain" in brain/ that knows
the seller's numbers and can take actions.

WHAT HAPPENS ON ONE CALL
  1. The web app creates a call row and a LiveKit room named after it (web/app/api/calls).
  2. LiveKit hands the room to this worker.              -> accept_only_our_calls()
  3. A warm process loads the seller and diagnoses them. -> entrypoint()
  4. Asha speaks. Each tool the model calls runs here.   -> class KamAgent
     Actions pass a consent check first.                 -> KamAgent._act()
  5. Everything said and done is saved as it happens.    -> class CallRecorder
  6. When the call ends the record is written, with a check of every figure she spoke.
                                                         -> CallRecorder._finish()

THIS FILE, IN ORDER
  Part 1  Settings
  Part 2  KamAgent        the agent, its consent gate and the tools the model can call
  Part 3  Voice           choosing Sarvam or Gemini Live and building the audio pipeline
  Part 4  CallRecorder    saving the transcript and the final call record
  Part 5  The worker      warm-up, accepting calls, and the per-call entry point

VOICE MODES (set VOICE_MODE, or choose per call on the call screen)
  sarvam  Sarvam speech-to-text -> Sarvam language model -> Sarvam text-to-speech (default)
  gemini  Gemini Live, a single speech-to-speech model (optional)

RUN IT
  python agent.py dev       wait for calls from the web app
  python agent.py console   talk to Asha in the terminal
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, function_tool

from brain import db, repo
from brain.audit import audit_call
from brain.consent import gate_report, seller_agreed
from brain.tools import KamTools
from prompts import build_instructions
from speech_filter import ReasoningFilter

load_dotenv()                                  # read agent/.env into the environment
log = logging.getLogger("kam-agent")


# ==============================================================================================
# Part 1. Settings
# ==============================================================================================

VOICE_MODE = os.environ.get("VOICE_MODE", "sarvam").lower()      # the default voice for a call
DEFAULT_SELLER = os.environ.get("DEFAULT_SELLER_ID", "S1")       # used only by console mode

# Published prices used for the per-call cost estimate on the dashboard, in rupees.
RATES = {
    "stt_per_hour": 29.40,            # Sarvam speech-to-text
    "tts_per_10k_chars": 30.00,       # Sarvam Bulbul v3 text-to-speech
    "tts_v4_per_10k_chars": 20.00,    # Sarvam Bulbul v4 Flash text-to-speech
    "llm_in_per_1m": 15.00,           # Sarvam 105B, per million input tokens
    "llm_out_per_1m": 60.00,          # Sarvam 105B, per million output tokens
    "gemini_live_per_min": 2.00,      # Gemini Live, approximate, from per-minute audio pricing
}

# Gemini Live models in order of preference; the first one the key can use is chosen.
GEMINI_LIVE_PREFERENCE = ("gemini-3.8-live", "gemini-live-2.5-flash-native-audio",
                          "gemini-3.1-flash-live-preview", "gemini-2.5-flash-native-audio-preview-12-2025")
GEMINI_HOST = "generativelanguage.googleapis.com"
GEMINI_API_VERSIONS = ("v1beta", "v1alpha", "v1")     # live audio is served on v1beta for most keys


async def db_call(fn, *args, **kwargs):
    """Run a database function without freezing the audio.

    The functions in brain/ are ordinary blocking code. Audio runs on one event loop, so a
    slow query there would make Asha stutter. This runs the function in a side thread."""
    return await asyncio.to_thread(fn, *args, **kwargs)


# ==============================================================================================
# Part 2. The agent, its consent gate and its tools
# ==============================================================================================

class KamAgent(Agent):
    """Asha. Holds the instructions, the tools the model may call, and the consent gate.

    The tool methods at the bottom are what the language model sees. Each one is a thin
    wrapper: the real work is in brain/tools.py (the `self.kam` object)."""

    # What the model is told when the consent gate refuses an action, by reason.
    BLOCKED = {
        "declined": "NOT DONE. The seller said no. Do not do this and do not ask again. Acknowledge it and move on.",
        "yes_was_about_something_else": "NOT DONE. The seller's yes was not about this action. Propose exactly this "
                                        "one action in a single sentence, then stop and wait for their answer.",
    }
    BLOCKED_DEFAULT = ("NOT DONE. The seller has not clearly said yes to this. Nothing was saved. Ask about this one "
                       "proposal in a single sentence, then stop and wait for their answer. Do not say it is done.")
    ACTIONS_PER_YES = 2          # one "yes" may authorise at most this many actions
    NOTES_PER_TURN = 2           # at most this many notes may be recorded from one thing the seller said

    def __init__(self, tools: KamTools, instructions: str, can_end_call: bool = True,
                 goodbye: Optional[str] = None):
        """`goodbye` is the exact farewell to speak when the call ends (see goodbye_line).
        Leave it out to let the model word its own goodbye, which the Gemini voice needs."""
        extra = []
        if can_end_call:
            # LiveKit's ready-made tool that lets Asha hang up. (Tests switch it off because
            # hanging up needs a real room.)
            from livekit.agents.beta.tools import EndCallTool
            extra.append(EndCallTool(
                extra_description="Use only after wrap_up has been called, the summary has been spoken, and the "
                                  "seller has said they need nothing else. Never use it mid-conversation. "
                                  "Call it once and say nothing more: the goodbye is spoken for you.",
                # With a fixed goodbye the model is not asked to write one. When it was, it
                # sometimes called end_call again instead, and the call ended in silence.
                end_instructions=None if goodbye else
                "Say a short, warm goodbye to the seller by name, in the language of the call.",
                ignore_on_enter=True,
                on_tool_called=self._on_end_call))
        super().__init__(instructions=instructions, tools=extra)
        self._goodbye = goodbye
        self._goodbye_said = False
        self.kam = tools                                # the brain: look-ups and actions for this seller
        self.dialogue: list[tuple[str, str]] = []       # ("seller" | "agent", text) in spoken order
        self._yes_used: dict[int, int] = {}             # dialogue position of a "yes" -> actions it has authorised
        self._noted: dict[int, int] = {}                # dialogue position -> notes recorded from it
        self.gate_log: list[tuple[str, str, str]] = []  # (action, "agreed" or why refused, the seller's words checked)

    async def _on_end_call(self, event) -> None:
        """Runs when the model hangs up: speak the goodbye, and let nothing cut it off.

        Two things went wrong here on live calls. A background sound was heard as speech and
        cut the goodbye off after three words. And when the model was asked to word the
        goodbye itself, it sometimes called end_call again instead and the line went dead."""
        try:
            event.ctx.disallow_interruptions()
        except Exception:               # already interrupted: nothing to protect
            pass
        if self._goodbye and not self._goodbye_said:
            self._goodbye_said = True
            try:
                # Queued behind the current turn. The session plays everything queued before it closes.
                event.ctx.session.say(self._goodbye, allow_interruptions=False)
            except Exception:
                log.exception("could not queue the goodbye")

    # ---- The consent gate: enforced in code, not left to the model --------------------------
    #
    # Why this exists: on a test call a model saved a restock plan, a stock buffer and dispatch
    # alerts while the seller was still asking a question. The instructions said "get a yes
    # first"; the model ignored them. So before any action is saved, the code below checks the
    # seller's own transcribed words. The rules for what counts as a yes are in brain/consent.py.

    def hear(self, text: str) -> None:
        """Record something the seller said. Called by CallRecorder for every seller utterance."""
        self.dialogue.append(("seller", text))

    def said(self, text: str) -> None:
        """Record something Asha said. Called by CallRecorder for every agent utterance."""
        self.dialogue.append(("agent", text))

    def _last_exchange(self) -> tuple[int, str, str]:
        """The seller's latest words and what Asha said just before them.

        Returns (position in the dialogue, seller's words, Asha's words before them),
        or (-1, "", "") if the seller has not spoken yet."""
        for j in range(len(self.dialogue) - 1, -1, -1):
            if self.dialogue[j][0] == "seller":
                before, k = [], j - 1
                while k >= 0 and self.dialogue[k][0] == "agent":   # Asha may have spoken in several pieces
                    before.insert(0, self.dialogue[k][1])
                    k -= 1
                return j, self.dialogue[j][1], " ".join(before)
        return -1, "", ""

    async def _consent(self, action: str) -> tuple[bool, str]:
        """Did the seller agree to this action? Returns (agreed, reason-if-not).

        Checks for a little over a second, because the transcript of the seller's reply can
        arrive just after the model has decided to act."""
        why = "nothing_heard"
        for _ in range(6):                                  # 6 checks, a fifth of a second apart
            position, seller_text, agent_before = self._last_exchange()
            if position >= 0:
                if self._yes_used.get(position, 0) >= self.ACTIONS_PER_YES:
                    why = "yes_already_used"
                else:
                    agreed, why = seller_agreed(seller_text, agent_before, action)
                    if agreed:
                        self._yes_used[position] = self._yes_used.get(position, 0) + 1
                        return True, ""
                    if why == "declined":                   # a clear no: no point waiting
                        return False, why
            await asyncio.sleep(0.2)
        return False, why

    async def _act(self, action: str, fn, *args, seller_confirmed: bool) -> dict[str, Any]:
        """Run one action tool, saving it only if the seller really agreed.

        action            the action's name for the consent check, for example "restock_plan"
        fn, *args         the brain method to call, and its arguments before seller_confirmed
        seller_confirmed  what the MODEL claims. It is treated as a claim and checked.

        If the claim does not hold, the brain method runs with seller_confirmed=False, which
        saves nothing and returns the proposal, and the model is told why it was refused."""
        if not seller_confirmed:
            return await db_call(fn, *args, False)
        agreed, why = await self._consent(action)
        self.gate_log.append((action, "agreed" if agreed else why, self._last_exchange()[1]))
        if agreed:
            return await db_call(fn, *args, True)
        log.warning("blocked %s: model claimed consent, seller did not give it (%s)", action, why)
        result = await db_call(fn, *args, False)
        if result.get("status") == "needs_confirmation":
            result["instruction"] = self.BLOCKED.get(why, self.BLOCKED_DEFAULT)
        return result

    def consent_report(self) -> dict[str, Any]:
        """What the consent gate allowed and refused on this call (see brain/consent.py)."""
        return gate_report(self.gate_log)

    # ---- Cleaning the model's words before they are spoken --------------------------------------

    async def llm_node(self, chat_ctx, tools, model_settings):
        """LiveKit calls this to get the model's reply as a stream of text pieces.

        We pass each piece through ReasoningFilter, so that if the model writes its private
        reasoning into the reply, it is removed before it is spoken or shown."""
        cleaner = ReasoningFilter()
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if isinstance(chunk, str):
                text = cleaner.feed(chunk)
                if text:
                    yield text
            elif getattr(chunk, "delta", None) is not None and chunk.delta.content:
                chunk.delta.content = cleaner.feed(chunk.delta.content)
                yield chunk
            else:                                           # tool calls and usage figures pass through
                yield chunk
        tail = cleaner.flush()
        if tail:
            yield tail

    # ---- Tools the model can call: look-ups (read-only) ------------------------------------------
    #
    # The text in each docstring below is sent to the language model. It is how the model
    # knows what a tool does and what its arguments mean.

    @function_tool
    async def get_stockout_products(self, limit: int = 5) -> dict[str, Any]:
        """List the products that ran out of stock this month, ranked by sales lost.

        Args:
            limit: How many products to return (1 to 10).
        """
        return await db_call(self.kam.stockout_products, limit)

    @function_tool
    async def get_cancellation_breakdown(self) -> dict[str, Any]:
        """Show who is cancelling (seller side or buyer side) and the top reasons."""
        return await db_call(self.kam.cancellation_breakdown)

    @function_tool
    async def get_pricing_gaps(self, limit: int = 5) -> dict[str, Any]:
        """List in-stock products where a rival is cheaper, ranked by sales lost.

        Args:
            limit: How many products to return (1 to 10).
        """
        return await db_call(self.kam.pricing_gaps, limit)

    @function_tool
    async def record_seller_input(self, topic: str, detail: str) -> dict[str, Any]:
        """Save something the seller explained, so it shapes the plan and is remembered next call.

        Args:
            topic: One of supplier_delay, cash_flow, missed_tracking, discontinued, pricing, dispatch, other.
            detail: What the seller said, in one sentence.
        """
        # Guard: the seller must actually have said something new. On a test call a model
        # asked "was it a supplier delay?" and recorded "supplier delay" without waiting.
        position, seller_text, _ = self._last_exchange()
        if position < 0 or len(seller_text.split()) < 2 or self._noted.get(position, 0) >= self.NOTES_PER_TURN:
            return {"status": "rejected", "instruction": "The seller has not said anything new to record. Record only "
                    "what the seller actually said. Ask your question, then stop and wait for the answer."}
        self._noted[position] = self._noted.get(position, 0) + 1
        return await db_call(self.kam.record_seller_input, topic, detail)

    # ---- Tools the model can call: actions (each needs the seller's yes) ---------------------------

    @function_tool
    async def create_restock_plan(self, top_n: int = 5, seller_confirmed: bool = False) -> dict[str, Any]:
        """Create a restock list for the products that lost the most sales by running out.

        Args:
            top_n: How many products to restock. Use fewer if the seller is short of cash.
            seller_confirmed: True only after the seller clearly said yes to this action.
        """
        return await self._act("restock_plan", self.kam.create_restock_plan, top_n, seller_confirmed=seller_confirmed)

    @function_tool
    async def pause_unavailable_listings(self, seller_confirmed: bool = False) -> dict[str, Any]:
        """Pause out-of-stock listings that are not being restocked, so they stop causing cancellations.

        Args:
            seller_confirmed: True only after the seller clearly said yes to this action.
        """
        # The False is `include_recently_out`: the model is not allowed to decide to pause
        # products that only ran out this month, because the seller may still restock them.
        return await self._act("pause_listings", self.kam.pause_unavailable_listings, False,
                               seller_confirmed=seller_confirmed)

    @function_tool
    async def set_stock_buffer(self, buffer_units: int = 2, seller_confirmed: bool = False) -> dict[str, Any]:
        """Set a safety stock buffer so listings switch off before stock reaches zero.

        Args:
            buffer_units: Units to hold back per product (1 to 10).
            seller_confirmed: True only after the seller clearly said yes to this action.
        """
        return await self._act("stock_buffer", self.kam.set_stock_buffer, buffer_units, seller_confirmed=seller_confirmed)

    @function_tool
    async def match_rival_prices(self, top_n: int = 5, max_discount_pct: float = 15,
                                 seller_confirmed: bool = False) -> dict[str, Any]:
        """Lower prices to match the cheapest rival on the products losing the most sales.

        Args:
            top_n: How many products to reprice.
            max_discount_pct: The largest price cut the seller's margin allows, in percent.
            seller_confirmed: True only after the seller clearly said yes to this action.
        """
        return await self._act("price_match", self.kam.match_rival_prices, top_n, max_discount_pct,
                               seller_confirmed=seller_confirmed)

    @function_tool
    async def enable_dispatch_alerts(self, seller_confirmed: bool = False) -> dict[str, Any]:
        """Turn on a daily pickup reminder and alerts before an order misses its dispatch deadline.

        Args:
            seller_confirmed: True only after the seller clearly said yes to this action.
        """
        return await self._act("dispatch_alerts", self.kam.enable_dispatch_alerts, seller_confirmed=seller_confirmed)

    # ---- Tools the model can call: housekeeping (no consent needed) --------------------------------

    @function_tool
    async def cancel_action(self, action: str = "all") -> dict[str, Any]:
        """Undo something saved on this call. Use it at once when the seller says they did not agree
        to it, did not want it, or has changed their mind.

        Args:
            action: One of all, restock_plan, pause_listings, stock_buffer, price_match, dispatch_alerts, ticket, followup.
        """
        return await db_call(self.kam.cancel_action, action)

    @function_tool
    async def raise_ticket(self, category: str, note: str) -> dict[str, Any]:
        """Ask the Snapdeal team to look at something, for example a visibility or rating review.

        Args:
            category: Short label such as "visibility review" or "catalogue quality".
            note: One or two sentences on what to check and why.
        """
        return await db_call(self.kam.raise_ticket, category, note)

    @function_tool
    async def schedule_followup(self, days: int = 7, on_date: str = "") -> dict[str, Any]:
        """Book the follow-up call. Call it again to move the follow-up when the seller asks for another day.

        Args:
            days: Days from today (1 to 30). Used when on_date is empty.
            on_date: A specific day as YYYY-MM-DD, when the seller names a date.
        """
        return await db_call(self.kam.schedule_followup, days, on_date or None)

    @function_tool
    async def escalate_to_human(self, category: str, reason: str) -> dict[str, Any]:
        """Hand over to a human account manager. Only for issues your tools cannot handle, or when the
        seller asks for a person. Never for thanks, goodbyes, or changing the follow-up date.

        Args:
            category: One of payments, account_or_policy, complaint_about_snapdeal, seller_asked_for_a_person, technical_problem, other.
            reason: Why this needs a person.
        """
        return await db_call(self.kam.escalate_to_human, category, reason)

    @function_tool
    async def wrap_up(self) -> dict[str, Any]:
        """Save the call summary. Call this once, just before you give the spoken summary."""
        return await db_call(self.kam.wrap_up)


# ==============================================================================================
# Part 3. Voice: choosing Sarvam or Gemini Live, and building the audio pipeline
# ==============================================================================================

async def list_gemini_live_models(api_key: str, timeout: float = 6.0) -> list[str]:
    """The models this Google key can use for live audio.

    Asks Google for its model list and keeps those that support "bidiGenerateContent",
    which is Google's name for a two-way live audio session."""
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as http:
        async with http.get(f"https://{GEMINI_HOST}/v1beta/models?pageSize=200",
                            headers={"X-goog-api-key": api_key}) as res:
            res.raise_for_status()
            models = (await res.json()).get("models", [])
    return [m["name"].split("/")[-1] for m in models
            if "bidiGenerateContent" in m.get("supportedGenerationMethods", [])]


async def probe_gemini_live(api_key: str, timeout: float = 6.0) -> Optional[str]:
    """Find the API version whose live-audio connection accepts this key (None if none does).

    Why: the Google library's default version is not always the one that serves live audio.
    Connecting with the wrong one fails with HTTP 404 and would kill the call, so we open
    and close a test connection before the call to find the version that works."""
    import aiohttp
    wanted = os.environ.get("GEMINI_API_VERSION", "").strip()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as http:
        for version in ((wanted,) if wanted else GEMINI_API_VERSIONS):
            url = f"wss://{GEMINI_HOST}/ws/google.ai.generativelanguage.{version}.GenerativeService.BidiGenerateContent"
            try:
                ws = await http.ws_connect(url, headers={"x-goog-api-key": api_key})
                await ws.close()
                return version
            except Exception as e:
                log.info("Gemini live endpoint %s not usable: %s", version, str(e)[:120])
    return None


def choose_gemini_model(available: list[str], wanted: str = "") -> Optional[str]:
    """Pick the Gemini Live model to use: the one asked for, else the first preferred model
    the key has, else any live model, else None."""
    if wanted:
        return wanted
    for name in GEMINI_LIVE_PREFERENCE:
        if name in available:
            return name
    return available[0] if available else None


async def resolve_voice(requested: Optional[str]) -> tuple[str, Optional[str], Optional[str]]:
    """Decide the voice for one call. Returns (mode, gemini model, gemini api version).

    `requested` is the voice picked on the call screen, or None for the default.
    Gemini is used only if the key works, a live model exists and a test connection
    succeeds. In every other case the call quietly runs on Sarvam, so a Gemini problem
    can never leave the seller in silence."""
    mode = (requested or VOICE_MODE or "sarvam").lower()
    if mode != "gemini":
        return "sarvam", None, None
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        log.warning("Gemini mode asked for but GOOGLE_API_KEY is empty; using Sarvam")
        return "sarvam", None, None
    try:
        model = choose_gemini_model(await list_gemini_live_models(key),
                                    os.environ.get("GEMINI_LIVE_MODEL", "").strip())
        version = await probe_gemini_live(key) if model else None
    except Exception as e:
        log.warning("could not reach Gemini (%s); using Sarvam for this call", e)
        return "sarvam", None, None
    if not model or not version:
        log.warning("Gemini live audio is not available for this key (model=%s, endpoint=%s); using Sarvam",
                    model, version)
        return "sarvam", None, None
    log.info("voice mode: Gemini Live, model %s, api %s", model, version)
    return "gemini", model, version


def build_session(language: str, mode: str = "sarvam", gemini_model: Optional[str] = None,
                  gemini_api_version: Optional[str] = None, vad=None) -> AgentSession:
    """Build the audio pipeline for one call.

    language   "en" or "hinglish": the language Asha replies in
    mode       "sarvam" or "gemini" (see resolve_voice)
    vad        the speech detector loaded at warm-up; loaded here if not given

    Sarvam mode is three models in a row: speech-to-text, a language model, text-to-speech.
    Gemini mode is one model that hears and speaks directly."""
    if mode == "gemini":
        from livekit.plugins import google
        return AgentSession(llm=google.realtime.RealtimeModel(
            model=gemini_model or GEMINI_LIVE_PREFERENCE[0],
            api_version=gemini_api_version or GEMINI_API_VERSIONS[0],
            voice=os.environ.get("GEMINI_VOICE", "Kore"), temperature=0.6))

    from livekit.agents import APIConnectOptions, SessionConnectOptions, stt as lk_stt, tts as lk_tts
    from livekit.plugins import sarvam, silero
    hinglish = language == "hinglish"
    vad = vad or silero.VAD.load()             # "voice activity detection": hears when someone is speaking

    # --- Ears: speech to text ---
    def sarvam_stt():
        """Sarvam speech-to-text. Sellers mix Hindi and English whatever reply language was
        picked, so it always listens for both ("codemix"). Set SARVAM_STT_LANGUAGE=en-IN to
        force English-only transcription."""
        forced = os.environ.get("SARVAM_STT_LANGUAGE", "").strip()
        return sarvam.STT(language=forced or "unknown",
                          model=os.environ.get("SARVAM_STT_MODEL", "saaras:v4"),
                          mode="transcribe" if forced else "codemix")

    # Live transcription over a websocket is fastest, but the connection can drop on a weak
    # network. If it does, fall back to transcribing each sentence over plain HTTPS.
    transport = os.environ.get("SARVAM_STT_TRANSPORT", "auto").lower()
    sentence_by_sentence = lk_stt.StreamAdapter(stt=sarvam_stt(), vad=vad)
    if transport == "http":
        speech_to_text = sentence_by_sentence
    elif transport == "ws":
        speech_to_text = sarvam_stt()
    else:
        speech_to_text = lk_stt.FallbackAdapter([sarvam_stt(), sentence_by_sentence], vad=vad)

    # --- Mouth: text to speech ---
    def sarvam_tts(model: str):
        """Sarvam text-to-speech with an Indian voice, in Hindi or Indian English."""
        # A touch quicker than the default pace: on live calls her turns felt slow and a full
        # call ran four minutes. Set SARVAM_TTS_PACE=1.0 for the voice's natural speed.
        return sarvam.TTS(target_language_code="hi-IN" if hinglish else "en-IN", model=model,
                          speaker=os.environ.get("SARVAM_TTS_SPEAKER") or None,
                          pace=float(os.environ.get("SARVAM_TTS_PACE", "1.1")))

    # The fast, cheaper voice model first; the older one takes over if it fails.
    tts_model = os.environ.get("SARVAM_TTS_MODEL", "").strip()
    if tts_model:
        text_to_speech = sarvam_tts(tts_model)
    else:
        text_to_speech = lk_tts.FallbackAdapter([sarvam_tts("bulbul:v4-flash"), sarvam_tts("bulbul:v3")])

    # --- Patience: retry a failing provider, and survive several errors before giving up ---
    retry = APIConnectOptions(max_retry=5, retry_interval=3.0, timeout=10.0)
    # The language model normally starts answering in about a third of a second. On a live
    # call it sometimes sent nothing at all, and waiting the full ten seconds twice gave a
    # 25-second silence. So give up on a silent request after a few seconds and ask again.
    llm_retry = APIConnectOptions(max_retry=5, retry_interval=0.3,
                                  timeout=float(os.environ.get("LLM_TIMEOUT_S", "4")))

    # --- Turn-taking: how long to wait before deciding the seller has finished speaking ---
    # When a sentence sounds unfinished the default wait is 2.5 seconds, which made short
    # answers like "ठीक है" feel slow. Raise ENDPOINT_MAX_DELAY if sellers get cut off mid-thought;
    # raise ENDPOINT_MIN_DELAY (e.g. 0.8) if even finished sentences get cut off.
    endpointing = {"max_delay": float(os.environ.get("ENDPOINT_MAX_DELAY", "1.6"))}
    min_delay = os.environ.get("ENDPOINT_MIN_DELAY", "").strip()
    if min_delay:
        endpointing["min_delay"] = float(min_delay)
    extra: dict[str, Any] = {"turn_handling": {"endpointing": endpointing}}

    return AgentSession(
        **extra,
        vad=vad,
        stt=speech_to_text,
        # --- Brain: the language model. Reasoning is off: "thinking" made replies slow and
        # leaked into speech on an early test call.
        llm=sarvam.LLM(model=os.environ.get("SARVAM_LLM_MODEL", "sarvam-105b"), temperature=0.4,
                       reasoning_effort=os.environ.get("SARVAM_REASONING_EFFORT", "none"),
                       max_tokens=400),
        tts=text_to_speech,
        conn_options=SessionConnectOptions(stt_conn_options=retry, llm_conn_options=llm_retry,
                                           tts_conn_options=retry, max_unrecoverable_errors=12),
    )


def noise_filter():
    """Optional filter that removes background voices and noise from the seller's audio.

    Off unless NOISE_CANCELLATION is set to "bvc" (background voices and noise) or "nc" (noise
    only), and it needs `pip install livekit-plugins-noise-cancellation` and LiveKit Cloud.
    It exists because a live call failed when a film playing in the room was heard as the
    seller speaking. It has not been tried on a live call yet, which is why it is opt-in."""
    choice = os.environ.get("NOISE_CANCELLATION", "").strip().lower()
    if choice not in ("bvc", "nc"):
        return None
    try:
        from livekit.plugins import noise_cancellation
        return noise_cancellation.BVC() if choice == "bvc" else noise_cancellation.NC()
    except Exception:
        log.warning("NOISE_CANCELLATION is set but the plugin could not be loaded; continuing without it")
        return None


def goodbye_line(owner_name: str, language: str) -> str:
    """The farewell Asha speaks as the call ends, by first name, in the language of the call."""
    first_name = (owner_name or "").split(" ")[0] or "ji"
    if language == "hinglish":
        return f"धन्यवाद {first_name} जी। अपना ध्यान रखिएगा, फिर बात करते हैं।"
    return f"Thank you, {first_name}. Take care, and we will talk again soon."


def estimate_cost(session: AgentSession, duration_s: int, mode: str = "sarvam") -> float:
    """A rupee estimate of what the call cost to run, for the dashboard.

    Sarvam mode adds up what the session reports it used (seconds of audio transcribed,
    characters spoken, tokens read and written) at the prices in RATES. Gemini mode is a
    flat per-minute estimate."""
    if mode == "gemini":
        return round(duration_s / 60 * RATES["gemini_live_per_min"], 2)
    cost = 0.0
    try:
        for usage in session.usage.model_usage:
            kind = type(usage).__name__
            if kind == "STTModelUsage":
                cost += (usage.audio_duration or 0) / 3600 * RATES["stt_per_hour"]
            elif kind == "TTSModelUsage":
                rate = RATES["tts_v4_per_10k_chars"] if "v4" in (usage.model or "") else RATES["tts_per_10k_chars"]
                cost += (usage.characters_count or 0) / 10000 * rate
            elif kind == "LLMModelUsage":
                cost += (usage.input_tokens or 0) / 1e6 * RATES["llm_in_per_1m"]
                cost += (usage.output_tokens or 0) / 1e6 * RATES["llm_out_per_1m"]
    except Exception:                 # reading usage must never break a call
        log.exception("could not read usage")
    if cost == 0.0:                   # nothing reported: fall back to the transcription cost of the call length
        cost = duration_s / 3600 * RATES["stt_per_hour"]
    return round(cost, 2)


# ==============================================================================================
# Part 4. Recording the call
# ==============================================================================================

# What the screen shows when Asha uses a tool, so her work is visible instead of hidden.
# A pair means (text when the action was saved, text when it was only proposed or refused).
TOOL_ACTIVITY = {
    "get_stockout_products": "Checked which products ran out of stock",
    "get_cancellation_breakdown": "Checked who is cancelling and why",
    "get_pricing_gaps": "Compared prices with rival sellers",
    "record_seller_input": "Noted what the seller explained",
    "create_restock_plan": ("Saved the restock plan", "Prepared a restock proposal"),
    "pause_unavailable_listings": ("Paused the out-of-stock listings", "Prepared to pause out-of-stock listings"),
    "set_stock_buffer": ("Set the safety stock buffer", "Prepared a safety stock buffer"),
    "match_rival_prices": ("Matched rival prices", "Prepared a price match proposal"),
    "enable_dispatch_alerts": ("Turned on dispatch alerts", "Prepared dispatch alerts"),
    "cancel_action": "Removed what the seller did not want",
    "raise_ticket": "Raised a ticket with the Snapdeal team",
    "schedule_followup": "Booked the follow-up call",
    "escalate_to_human": ("Handed over to a human account manager", "Decided a human is not needed"),
    "wrap_up": "Saved the call summary",
    "end_call": "Ended the call",
}
SAVED_STATUSES = ("done", "updated", "rescheduled", "already_done")


def describe_tool_activity(name: str, output: str | None) -> Optional[str]:
    """The short line to show on screen for one tool call, or None for a tool we do not show.

    `output` is the tool's result as text; its "status" tells us whether the action was
    actually saved or only proposed."""
    label = TOOL_ACTIVITY.get(name)
    if label is None:
        return None
    if isinstance(label, tuple):
        result = output or ""
        saved = any(f'"status": "{st}"' in result or f"'status': '{st}'" in result for st in SAVED_STATUSES)
        return label[0] if saved else label[1]
    return label


class CallRecorder:
    """Saves the transcript as it happens, and writes the call record when the call ends.

    It listens to three events from the session:
      conversation_item_added   someone finished saying something
      function_tools_executed   Asha used one or more tools
      close                     the call is over
    """

    def __init__(self, session: AgentSession, call_id: str, tools: KamTools, on_done=None,
                 mode: str = "sarvam", agent: Optional["KamAgent"] = None):
        self.session, self.call_id, self.tools = session, call_id, tools
        self.on_done = on_done                # called after the record is saved (frees the worker)
        self.mode = mode                      # "sarvam" or "gemini", for the cost estimate
        self.agent = agent                    # told what was said, so its consent gate can work
        self.started = datetime.now(timezone.utc)
        self.reply_delays: list[float] = []   # seconds from the seller stopping to Asha starting, per reply
        self.agent_said: list[str] = []       # everything Asha said, for the figure check
        self.references: list[str] = []       # the brief and every tool result: where her figures may come from
        self.close_reason: Optional[str] = None
        self._finish_task: Optional[asyncio.Future] = None
        # One background writer saves transcript lines in spoken order, off the audio loop.
        self._turns: asyncio.Queue[Optional[tuple[str, str]]] = asyncio.Queue()
        self._writer = asyncio.create_task(self._write_turns())
        session.on("conversation_item_added", self._on_item)
        session.on("close", self._on_close)
        session.on("function_tools_executed", self._on_tools)

    async def _write_turns(self) -> None:
        """Background task: save queued transcript lines one at a time, until told to stop (None)."""
        while True:
            item = await self._turns.get()
            if item is None:
                return
            try:
                await db_call(repo.add_turn, self.call_id, *item)
            except Exception:
                log.exception("could not save a transcript turn")

    def _on_item(self, ev) -> None:
        """Someone finished speaking: queue the line for saving and tell the consent gate."""
        item = ev.item
        role = getattr(item, "role", None)                  # "user" is the seller, "assistant" is Asha
        if role not in ("user", "assistant"):
            return
        text = getattr(item, "text_content", None) or ""
        if text.strip():
            self._turns.put_nowait(("seller" if role == "user" else "agent", text))
            if role == "assistant":
                self.agent_said.append(text)
            if self.agent is not None:
                (self.agent.hear if role == "user" else self.agent.said)(text)
        if role == "assistant":
            # LiveKit measures, for each reply, how long the seller waited for it.
            timing = getattr(item, "metrics", None) or {}
            delay = timing.get("e2e_latency")
            if delay:
                self.reply_delays.append(delay)
                log.info("reply started %.2fs after the seller stopped (model first words %.2fs, voice %.2fs)",
                         delay, timing.get("llm_node_ttft") or 0, timing.get("tts_node_ttfb") or 0)

    def _on_tools(self, ev) -> None:
        """Asha used tools: show each one on screen, and keep the results for the figure check."""
        outputs = {o.call_id: o.output for o in (ev.function_call_outputs or []) if o is not None}
        self.references += [str(o) for o in outputs.values() if o]
        for call in ev.function_calls or []:
            text = describe_tool_activity(call.name, outputs.get(call.call_id))
            if text:
                self._turns.put_nowait(("tool", text))

    def _on_close(self, ev) -> None:
        """The call is over: save the record, then let the worker go."""
        self.close_reason = getattr(getattr(ev, "reason", None), "value", None)

        async def save_then_release() -> None:
            """Save first, release second: the record must be written before the worker goes."""
            await self.finish()
            if self.on_done and self.close_reason != "job_shutdown":
                self.on_done()

        self._closing = asyncio.create_task(save_then_release())

    async def finish(self) -> None:
        """Write the call record, exactly once.

        Safe to call from several places (the close event and the worker's shutdown hook):
        later callers wait for the first one to complete, so the worker never exits before
        the record is saved."""
        if self._finish_task is None:
            self._finish_task = asyncio.ensure_future(self._finish())
        await asyncio.shield(self._finish_task)

    async def _finish(self) -> None:
        """Save the last transcript lines, then the summary, figure check, consent record, cost and timing."""
        self._turns.put_nowait(None)          # tell the writer to stop after what is queued
        await self._writer
        ended = datetime.now(timezone.utc)
        duration = int((ended - self.started).total_seconds())

        # Rebuilt from the database, so it is right even if something changed after the spoken summary.
        summary = await db_call(self.tools.build_summary)
        if self.close_reason == "error":
            summary["ended_reason"] = "connection_problem"
        elif self.agent is not None and not any(role == "seller" for role, _ in self.agent.dialogue):
            summary["ended_reason"] = "no_conversation"      # the seller left before saying anything

        # Compare every rupee figure Asha spoke with the figures she was given (brain/audit.py).
        try:
            summary["audit"] = audit_call(self.agent_said, self.references)
        except Exception:
            log.exception("figure check failed")

        # What the consent gate allowed and refused (KamAgent.consent_report).
        try:
            if self.agent is not None:
                summary["consent"] = self.agent.consent_report()
        except Exception:
            log.exception("consent report failed")

        delays = self.reply_delays
        await db_call(repo.update_call, self.call_id, status="ended", ended_at=ended, duration_s=duration,
                      est_cost_inr=estimate_cost(self.session, duration, self.mode),
                      avg_latency_ms=int(sum(delays) / len(delays) * 1000) if delays else None,
                      summary=summary)


# ==============================================================================================
# Part 5. The worker: warm-up, accepting calls, and the per-call entry point
# ==============================================================================================

def keep_database_warm(every_s: float = 20.0) -> None:
    """Keep one database connection open and recently used, in a background thread.

    On a live call the very first database look-up took over four seconds, because the
    connection had to be opened from cold at the moment the seller was waiting. This thread
    opens it in advance and touches it every few seconds so it never goes cold."""
    def touch_forever() -> None:
        while True:
            try:
                with db.engine().connect() as connection:
                    connection.exec_driver_sql("select 1")
            except Exception:           # the database may be starting up; try again next round
                pass
            time.sleep(every_s)
    threading.Thread(target=touch_forever, daemon=True, name="db-keep-warm").start()


def prewarm(proc) -> None:
    """Runs once when a worker process starts, before any call reaches it.

    Loading the voice libraries and the speech detector takes several seconds. Doing it here,
    in a process kept ready in advance, means that work is not done while the seller waits.
    The log line "call set up in ..." shows how long each call actually took to start."""
    from livekit.plugins import silero
    proc.userdata["vad"] = silero.VAD.load()
    for module in ("livekit.plugins.sarvam", "livekit.plugins.google", "openai.types.audio",
                   "openai.types.realtime", "livekit.agents.beta.tools", "aiohttp"):
        try:
            __import__(module)
        except Exception:           # optional pieces must never stop a worker from starting
            pass
    try:
        db.create_schema()
        with db.engine().connect():  # open the database connection ahead of the first call
            pass
    except Exception:
        log.exception("database not reachable during warm-up")
    keep_database_warm()


# One process is always kept warm, so a call never waits for Python to start.
server = AgentServer(setup_fnc=prewarm, initialize_process_timeout=60.0,
                     num_idle_processes=int(os.environ.get("AGENT_WARM_PROCESSES", "1")))

# The main worker process decides whether to accept each call, which needs the database too.
server.on("worker_started", lambda *_: keep_database_warm())


async def accept_only_our_calls(req) -> None:
    """Decide whether this worker should take a call. It takes only calls it can see in
    its own database.

    Why: if a laptop worker and a cloud worker are both connected to the same LiveKit
    project, each call must go to the one that shares the web app's database. A worker that
    cannot find the call declines it, and LiveKit offers it to another worker."""
    room = req.room.name or ""
    began = time.monotonic()
    try:
        known = not room.startswith("call_") or await db_call(repo.get_call, room) is not None
        if not known:                       # allow for a row that is still being committed
            await asyncio.sleep(0.5)
            known = await db_call(repo.get_call, room) is not None
    except Exception:
        log.exception("could not check the call record; accepting the call")
        known = True
    if not known:
        log.warning("declining %s: this worker's database has no record of it", room)
        await req.reject(terminate=False)
        return
    log.info("accepting %s (checked in %.1fs)", room, time.monotonic() - began)
    await req.accept()


@server.rtc_session(on_request=accept_only_our_calls)
async def entrypoint(ctx: JobContext) -> None:
    """Runs once per call, in its own process. Sets everything up, then starts Asha talking."""
    began = time.monotonic()
    await ctx.connect()
    joined = time.monotonic()
    if "vad" not in ctx.proc.userdata:          # console mode, or warm-up was skipped
        await db_call(db.create_schema)

    # 1. Which call is this? The room name is the call id; the call row says which seller,
    #    which language, and whether Asha is calling first.
    call_id = ctx.room.name
    call = await db_call(repo.get_call, call_id)
    if call is None:                            # console mode: no web app created a call row
        await db_call(repo.create_call, DEFAULT_SELLER, "inbound", call_id)
        call = await db_call(repo.get_call, call_id)

    # 2. Load the seller and diagnose them. This happens before Asha says a word.
    tools = await db_call(KamTools, call["seller_id"], call_id)

    # 3. Choose the voice, then write Asha's instructions for this seller.
    mode, gemini_model, gemini_api = await resolve_voice(call.get("voice_mode"))
    language = call.get("language") or "en"
    prompt_language = language
    if mode == "gemini":                        # Gemini speaks rather than writes, so it gets its own rule
        prompt_language = "hinglish_voice" if language == "hinglish" else "auto"
    memory = await db_call(tools.memory_brief)             # what was agreed last time, if anything
    brief = await db_call(tools.account_brief)             # numbers, diagnosis and playbook
    instructions = build_instructions(brief, memory, call["direction"], prompt_language)
    briefed = time.monotonic()

    # 4. Build the audio pipeline, the agent, and the recorder that saves everything.
    session = build_session(language, mode, gemini_model, gemini_api, vad=ctx.proc.userdata.get("vad"))
    # The Sarvam voice speaks a fixed goodbye. Gemini speaks for itself, so it words its own.
    goodbye = None if mode == "gemini" else goodbye_line(tools.seller["owner_name"], language)
    kam_agent = KamAgent(tools, instructions, goodbye=goodbye)
    recorder = CallRecorder(session, call_id, tools, mode=mode, agent=kam_agent,
                            on_done=lambda: ctx.shutdown(reason="call ended"))  # frees the worker at once
    recorder.references += [brief, memory or ""]
    ctx.add_shutdown_callback(recorder.finish)     # safety net if the job is stopped another way

    # 5. Go live: mark the call, join the room, and have Asha speak first.
    await db_call(repo.update_call, call_id, status="live", started_at=recorder.started, voice_mode=mode)
    cleaner = noise_filter()
    if cleaner is not None:
        from livekit.agents.voice import room_io
        await session.start(agent=kam_agent, room=ctx.room, room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(noise_cancellation=cleaner)))
    else:
        await session.start(agent=kam_agent, room=ctx.room)
    log.info("call set up in %.1fs (join room %.1f, load seller %.1f, start voice %.1f)",
             time.monotonic() - began, joined - began, briefed - joined, time.monotonic() - briefed)
    await session.generate_reply(instructions="Start the call now with the opening described in CALL FLOW step 1.")
    asyncio.create_task(db_call(repo.close_stale_calls))   # housekeeping, off the seller's critical path


if __name__ == "__main__":
    agents.cli.run_app(server)
