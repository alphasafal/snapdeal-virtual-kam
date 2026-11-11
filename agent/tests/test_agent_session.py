"""Runs the real agent class in a text-only session with a scripted LLM (no audio, no keys).

Checks the wiring a unit test cannot: leaked reasoning never reaches the transcript,
a tool call made by the model saves an action, and closing the session writes the call record.
"""
import asyncio
import json

import pytest
from livekit.agents import AgentSession, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

BAR = "=" * 80


class ScriptedLLM(llm.LLM):
    """Returns the next scripted step each time the agent asks for a completion."""

    def __init__(self, steps):
        super().__init__()
        self.steps = list(steps)

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        step = self.steps.pop(0) if self.steps else {"text": "Okay."}
        return ScriptedStream(self, step, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class ScriptedStream(llm.LLMStream):
    def __init__(self, model, step, **kwargs):
        super().__init__(model, **kwargs)
        self.step = step

    async def _run(self) -> None:
        if "tool" in self.step:
            name, args = self.step["tool"]
            delta = llm.ChoiceDelta(role="assistant", tool_calls=[
                llm.FunctionToolCall(name=name, arguments=json.dumps(args), call_id="call_1")])
            self._event_ch.send_nowait(llm.ChatChunk(id="c", delta=delta))
            return
        text = self.step["text"]
        for i in range(0, len(text), 9):          # stream in small pieces, like a real model
            self._event_ch.send_nowait(llm.ChatChunk(
                id="c", delta=llm.ChoiceDelta(role="assistant", content=text[i:i + 9])))


@pytest.mark.asyncio
async def test_text_session_filters_reasoning_saves_action_and_closes_call(fresh_db):
    import agent
    from brain import repo
    from brain.tools import KamTools
    from prompts import build_instructions

    call_id = repo.create_call("S1")
    tools = KamTools("S1", call_id)
    script = ScriptedLLM([
        {"text": f"{BAR}\nThe seller asks why. I should explain.\n{BAR}\n\nYour sales fell because products ran out."},
        {"tool": ("create_restock_plan", {"top_n": 4, "seller_confirmed": True})},
        {"text": "Done, the restock list for four products is saved."},
    ])
    session = AgentSession(llm=script)
    kam = agent.KamAgent(tools, build_instructions(tools.account_brief(), None, "inbound", "en"),
                         can_end_call=False)      # hanging up needs a real LiveKit room
    recorder = agent.CallRecorder(session, call_id, tools, agent=kam)
    await session.start(agent=kam)

    await session.run(user_input="Why did my sales drop?")
    await session.run(user_input="Yes, restock the top four.")
    await session.aclose()
    await asyncio.wait_for(recorder.finish(), 5)

    turns = repo.get_turns(call_id)
    spoken = [t["text"] for t in turns if t["role"] == "agent"]
    assert spoken[0] == "Your sales fell because products ran out."        # reasoning stripped
    assert not any("=" in t or "I should" in t for t in spoken)
    assert [t["role"] for t in turns][:2] == ["seller", "agent"]            # saved in spoken order
    assert "Saved the restock plan" in [t["text"] for t in turns if t["role"] == "tool"]   # visible tool use
    actions = repo.get_actions(call_id=call_id)
    assert [a["type"] for a in actions] == ["restock_plan"] and len(actions[0]["detail"]["products"]) == 4
    call = repo.get_call(call_id)
    assert call["status"] == "ended" and call["summary"]["actions"][0]["title"].startswith("Restock 4")


def test_production_agent_can_hang_up(fresh_db):
    import agent
    from brain import repo
    from brain.tools import KamTools

    kam = agent.KamAgent(KamTools("S1", repo.create_call("S1")), "instructions")
    names = set()
    for t in kam.tools:
        names |= {getattr(x, "name", None) or x.info.name for x in getattr(t, "tools", [t])}
    assert {"end_call", "wrap_up", "cancel_action", "create_restock_plan", "schedule_followup"} <= names
    assert len(names) == 15


@pytest.mark.asyncio
async def test_model_cannot_act_without_the_sellers_yes(fresh_db):
    """Replays what went wrong on a real call: the model claimed consent the seller never gave."""
    import agent
    from brain import repo
    from brain.tools import KamTools

    call_id = repo.create_call("S1")
    tools = KamTools("S1", call_id)
    script = ScriptedLLM([
        {"tool": ("create_restock_plan", {"top_n": 5, "seller_confirmed": True})},   # seller only asked a question
        {"text": "Shall I create a restock plan for your top five products?"},
        {"tool": ("record_seller_input", {"topic": "supplier_delay", "detail": "Supplier delay"})},  # never said
        {"text": "Understood. Shall I create a restock plan for your top five products instead?"},
        {"tool": ("create_restock_plan", {"top_n": 5, "seller_confirmed": True})},   # now the seller agreed
        {"text": "Done, the restock plan is saved."},
    ])
    session = AgentSession(llm=script)
    kam = agent.KamAgent(tools, "instructions", can_end_call=False)
    recorder = agent.CallRecorder(session, call_id, tools, agent=kam)
    await session.start(agent=kam)

    await session.run(user_input="How much did you say? I did not understand the figures.")
    assert repo.get_actions(call_id=call_id) == []                 # blocked: a question is not a yes
    await session.run(user_input="No, I do not want anything.")
    assert repo.get_actions(call_id=call_id) == []
    await session.run(user_input="Okay, yes, do it.")
    assert [a["type"] for a in repo.get_actions(call_id=call_id)] == ["restock_plan"]
    await session.aclose()
    await asyncio.wait_for(recorder.finish(), 5)
    shown = [t["text"] for t in repo.get_turns(call_id) if t["role"] == "tool"]
    assert shown.count("Saved the restock plan") == 1 and "Prepared a restock proposal" in shown


@pytest.mark.asyncio
async def test_seller_can_undo_and_every_call_gets_a_figure_check(fresh_db):
    import agent
    from brain import repo
    from brain.tools import KamTools

    call_id = repo.create_call("S1")
    tools = KamTools("S1", call_id)
    script = ScriptedLLM([
        {"text": "Shall I create a restock plan for your top five products?"},
        {"tool": ("create_restock_plan", {"top_n": 5, "seller_confirmed": True})},
        {"text": "Done. Your sales fell from six lakh rupees to one lakh thirty-five thousand rupees."},  # wrong figure
        {"tool": ("cancel_action", {"action": "restock_plan"})},
        {"text": "It is removed. Nothing will happen without your yes."},
    ])
    session = AgentSession(llm=script)
    kam = agent.KamAgent(tools, "instructions", can_end_call=False)
    recorder = agent.CallRecorder(session, call_id, tools, agent=kam)
    recorder.references.append(tools.account_brief())
    await session.start(agent=kam)

    await session.run(user_input="What do you suggest?")
    await session.run(user_input="Yes, go ahead.")
    assert len(repo.get_actions(call_id=call_id)) == 1
    await session.run(user_input="Actually I changed my mind, remove it.")
    assert repo.get_actions(call_id=call_id) == []                      # undone
    await session.aclose()
    await asyncio.wait_for(recorder.finish(), 5)

    summary = repo.get_call(call_id)["summary"]
    assert summary["actions"] == [] and summary["cancelled"] == ["Restock 5 top products"]
    assert [f["value"] for f in summary["audit"]["flags"]] == [600000]  # "six lakh" is not in the data
    assert summary["audit"]["figures_checked"] == 2


@pytest.mark.asyncio
async def test_worker_declines_calls_from_another_database(fresh_db):
    """A laptop worker and a cloud worker can share one LiveKit project without stealing calls."""
    import agent
    import livekit.agents as lk
    from brain import repo
    from livekit.protocol import agent as agent_proto, models

    async def decide(room: str) -> dict:
        seen: dict = {}

        async def on_reject(terminate: bool = True) -> None:
            seen["rejected"] = terminate

        async def on_accept(args) -> None:
            seen["accepted"] = True

        job = agent_proto.Job(id="AJ_test", room=models.Room(name=room, sid="RM_test"), type=agent_proto.JobType.JT_ROOM)
        await agent.accept_only_our_calls(lk.JobRequest(job=job, on_reject=on_reject, on_accept=on_accept))
        return seen

    assert await decide("call_from_somewhere_else") == {"rejected": False}   # left for the right worker
    assert await decide(repo.create_call("S1")) == {"accepted": True}
    assert await decide("console-room") == {"accepted": True}


# ---- Hanging up ---------------------------------------------------------------------------
# On live calls the model, asked to word its own goodbye, sometimes called end_call again
# instead and the line went dead. The goodbye is now a fixed line queued by code.

class _FakeSession:
    def __init__(self):
        self.spoken = []

    def say(self, text, allow_interruptions=True):
        self.spoken.append((text, allow_interruptions))


class _FakeRunContext:
    def __init__(self):
        self.session = _FakeSession()
        self.protected = 0

    def disallow_interruptions(self):
        self.protected += 1


class _FakeEvent:
    def __init__(self):
        self.ctx = _FakeRunContext()


@pytest.mark.asyncio
async def test_goodbye_is_spoken_once_and_cannot_be_interrupted(fresh_db):
    import agent
    from brain import repo
    from brain.tools import KamTools
    tools = KamTools("S1", repo.create_call("S1"))
    kam = agent.KamAgent(tools, "instructions", can_end_call=False, goodbye=agent.goodbye_line("Rajesh Sharma", "en"))
    first, second = _FakeEvent(), _FakeEvent()
    await kam._on_end_call(first)
    await kam._on_end_call(second)                 # the model calling end_call twice in a row
    assert first.ctx.session.spoken == [("Thank you, Rajesh. Take care, and we will talk again soon.", False)]
    assert second.ctx.session.spoken == []         # no second goodbye
    assert first.ctx.protected == 1


@pytest.mark.asyncio
async def test_without_a_fixed_goodbye_the_model_words_its_own(fresh_db):
    import agent
    from brain import repo
    from brain.tools import KamTools
    tools = KamTools("S1", repo.create_call("S1"))
    kam = agent.KamAgent(tools, "instructions", can_end_call=False)     # the Gemini voice path
    event = _FakeEvent()
    await kam._on_end_call(event)
    assert event.ctx.session.spoken == [] and event.ctx.protected == 1


def test_goodbye_line_follows_the_language_of_the_call():
    import agent
    assert agent.goodbye_line("Meena Patel", "hinglish").startswith("धन्यवाद Meena जी")
    assert agent.goodbye_line("Meena Patel", "en").startswith("Thank you, Meena.")
