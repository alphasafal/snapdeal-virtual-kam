"""What counts as the seller saying yes. Several cases are lines from real test calls."""
import pytest
from brain.consent import is_clear_yes

YES = ["Yes, please.", "Yes, do it.", "Yes, please do that also.", "Okay, but only the top four. Yes, do it.",
       "हां बिल्कुल बताइए।".replace("बताइए", "कर दीजिए"), "बिल्कुल बना दीजिए।", "Haan kar do", "theek hai", "ठीक है",
       "Sure, go ahead", "ok", "Ji haan", "हाँ जी", "Please do that. What happens next?"]
NO = ["",                                                                    # nothing heard
      "अच्छा जी, आपने कितना बोला? मेरे को फिगर्स समझ नहीं आया। आपने 6 लाख बोला।",       # from a real call: a question
      "ठीक है, हर्षद जी। तो बताइए अब क्या दिक्कत आ रही है और?",                          # from a real call: filler then a question
      "Asha ji, mere ko ismein se kuch nahi chahiye. Maine kuch bhi agree nahi kara.",   # from a real call: a refusal
      "No, thank you.", "Nahi, abhi mat karo", "Wait, will pausing hurt my ranking?", "What does that cost?",
      "I don't want to discuss this more.", "My supplier delayed the shipment by two weeks.", "Maybe later",
      "Actually cash flow की दिक्कत थी।", "Okay, but why?", "हां लेकिन ये क्या है?"]


@pytest.mark.parametrize("text", YES)
def test_clear_yes(text):
    assert is_clear_yes(text)


@pytest.mark.parametrize("text", NO)
def test_not_a_yes(text):
    assert not is_clear_yes(text)


from brain.consent import seller_agreed  # noqa: E402


@pytest.mark.parametrize("seller,agent_before,action,agreed,why", [
    ("Yes, please.", "I will set up a daily pickup reminder and dispatch alerts. Should I turn that on?", "dispatch_alerts", True, ""),
    ("Yes", "Shall I pause the other listings and keep a two-unit safety buffer?", "pause_listings", True, ""),
    ("Yes", "Shall I pause the other listings and keep a two-unit safety buffer?", "stock_buffer", True, ""),
    ("हाँ कर दीजिए", "क्या मैं top चार products का restock plan बना दूँ?", "restock_plan", True, ""),
    ("please restock my top five products", "How can I help you today?", "restock_plan", True, ""),
    ("restock kar do", "", "restock_plan", True, ""),
    # the hole this closes: a yes that answered a different question
    ("haan", "Kya ye supplier delay ki wajah se hua hai?", "restock_plan", False, "yes_was_about_something_else"),
    ("Yes, please.", "Should I turn on dispatch alerts?", "price_match", False, "yes_was_about_something_else"),
    ("What is this restock plan? Can you explain?", "Shall I create a restock plan?", "restock_plan", False, "no_clear_yes"),
    ("restock mat karo", "Shall I create a restock plan?", "restock_plan", False, "declined"),
    ("No. I don't want it.", "Shall I proceed with this restock plan?", "restock_plan", False, "declined"),
    ("Any recommendation from your side?", "Your sales this month are one lakh thirty-five thousand rupees.", "restock_plan", False, "no_clear_yes"),
    ("", "Shall I create a restock plan?", "restock_plan", False, "nothing_heard"),
])
def test_consent_is_tied_to_the_action(seller, agent_before, action, agreed, why):
    assert seller_agreed(seller, agent_before, action) == (agreed, why)


# ---- Lines from the live Hindi call of 10 November ------------------------------------------
# Three of these were wrongly refused on that call, so Asha asked the same question again.
# Cause 1: speech-to-text ends Hindi sentences with "।", which was being read as a letter.
# Cause 2: speech-to-text wrote one "ठीक है" in Gurmukhi script.

RESTOCK_ASK = "क्या हम top 5 products का restock plan बना लें?"
ALERTS_ASK = "अब मैं dispatch alert enable कर दूँ, जिससे daily pickup reminder मिल जाएगा। ठीक है?"


@pytest.mark.parametrize("seller,agent_before,action", [
    ("जी बना दीजिए।", RESTOCK_ASK, "restock_plan"),         # refused on the call
    ("कर दीजिए।", ALERTS_ASK, "dispatch_alerts"),           # refused on the call
    ("ਠੀਕ ਹੈ।", ALERTS_ASK, "dispatch_alerts"),             # refused on the call (Gurmukhi script)
    ("बिल्कुल बिल्कुल।", RESTOCK_ASK, "restock_plan"),
    ("कर दो कर दो।", ALERTS_ASK, "dispatch_alerts"),
    ("ठीक है।", ALERTS_ASK, "dispatch_alerts"),
    ("हाँ जी, कर दो ना।", ALERTS_ASK, "dispatch_alerts"),    # "ना" here is a friendly tag, not a no
])
def test_hindi_yes_from_speech_to_text(seller, agent_before, action):
    assert seller_agreed(seller, agent_before, action) == (True, "")


@pytest.mark.parametrize("seller,why", [
    ("नहीं।", "declined"),
    ("नहीं, अभी रहने दीजिए।", "declined"),
    ("मत कीजिए।", "declined"),
    ("मुझे ये चीज़ पसंद नहीं आई।", "declined"),
    ("थोड़ा बता दीजिए।", "no_clear_yes"),                    # "tell me a bit" is not a yes
    ("इससे क्या होगा?", "no_clear_yes"),
    ("ठीक है, पर इससे कितना फायदा होगा?", "no_clear_yes"),
])
def test_hindi_no_or_question_from_speech_to_text(seller, why):
    assert seller_agreed(seller, ALERTS_ASK, "dispatch_alerts") == (False, why)


def test_tidy_maps_sister_scripts_and_drops_sentence_marks():
    from brain.consent import tidy
    assert tidy("ਠੀਕ ਹੈ।") == " ठीक है "
    assert tidy("कर दीजिए।") == " कर दीजिए "
    assert tidy("Okay, but why?") == " okay but why? "       # the question mark is kept
