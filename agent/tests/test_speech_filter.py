"""The filter that keeps a model's leaked reasoning out of what is spoken."""
from speech_filter import ReasoningFilter

BAR = "=" * 80


def run(chunks):
    f = ReasoningFilter()
    return "".join(f.feed(c) for c in chunks) + f.flush()


def test_plain_reply_is_untouched():
    assert run(["Namaste Rajesh ji, ", "how can I help?"]) == "Namaste Rajesh ji, how can I help?"


def test_fenced_reasoning_is_dropped():
    text = f"{BAR}\nThe seller is asking what happened.\nI need to answer.\n{BAR}\n\nYour sales fell this month."
    assert run([text]) == "Your sales fell this month."


def test_fenced_reasoning_dropped_when_streamed_in_small_chunks():
    text = f"{BAR}\nThinking about it.\n{BAR}\nYour sales fell."
    assert run([text[i:i + 7] for i in range(0, len(text), 7)]) == "Your sales fell."


def test_only_reasoning_gives_silence():
    assert run([f"{BAR}\nStill thinking"]) == ""


def test_stray_bars_removed_mid_reply():
    assert run(["Okay. ", BAR, " Done."]) == "Okay.  Done."
