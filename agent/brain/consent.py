"""Did the seller actually say yes?

The language model is told to act only after a clear yes, but a model can ignore an
instruction. So the check is done here in code, on the seller's own transcribed words,
before any action is saved. It is deliberately strict: when unsure, the answer is no,
and the agent asks again. English, Hindi (Devanagari) and Roman Hinglish are covered.

Two things learned from a real call are handled by `tidy()` below:
  - Speech-to-text ends Hindi sentences with the full stop "।". That mark sits inside the
    Devanagari block, so "कर दीजिए।" was not recognised as ending in the word "दीजिए".
  - Speech-to-text sometimes writes Hindi in a neighbouring script (a plain "ठीक है" came
    back in Gurmukhi as "ਠੀਕ ਹੈ"). Those scripts are mapped onto Devanagari first.
"""
from __future__ import annotations

import re

# Phrases that clearly ask for the action to be done. These win even if a question follows.
STRONG_YES = [
    "kar do", "kar dijiye", "kar dijie", "kar dena", "kardo", "kar de", "bana do", "bana dijiye", "bana dijie",
    "laga do", "chalu kar", "ho jaye", "kijiye", "kijie", "kar lo", "kar lijiye", "kar dein", "bana lo",
    "bana dein", "on kar", "shuru kar",
    "कर दो", "कर दीजिए", "कर दीजिये", "कर देना", "कर दें", "बना दो", "बना दीजिए", "बना दीजिये", "लगा दो",
    "चालू कर", "कीजिए", "कीजिये", "कर लो", "कर लीजिए", "कर लीजिये", "बना लो", "बना लीजिए", "बना दें",
    "लगा दीजिए", "लगा दीजिये", "शुरू कर", "हो जाए", "कर देते हैं", "बना देते हैं",
    "do it", "go ahead", "please do", "do that", "set it up", "turn it on", "create it", "make it", "book it",
]
YES_WORDS = [
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "okey", "alright", "fine", "agreed", "correct", "right",
    "absolutely", "definitely", "confirm", "confirmed", "proceed",
    "haan", "han", "haa", "ha", "hanji", "haanji", "bilkul", "theek", "thik", "sahi", "zaroor", "jaroor", "chalega",
    "हाँ", "हां", "हा", "जी हाँ", "जी हां", "बिल्कुल", "ठीक", "सही", "ज़रूर", "जरूर", "चलेगा",
    "हाँ जी", "हां जी", "जी बिल्कुल", "ठीक है", "सही है", "चलो", "चलिए", "अच्छा ठीक", "डन",
    "यस", "येस", "ओके", "श्योर",
]
NO_WORDS = [
    "no", "nope", "not", "don't", "dont", "do not", "never", "stop", "wait", "cancel", "later", "nothing",
    "nahi", "nahin", "nai", "mat", "ruk", "ruko", "rehne", "baad", "kuch nahi",
    "नहीं", "नही", "मत", "रुक", "रुको", "रुकिए", "रहने", "बाद में", "कुछ नहीं", "अभी नहीं",
]
QUESTION_WORDS = [
    "what", "why", "how", "which", "when", "who", "how much", "explain", "tell me", "understand",
    "kya", "kyu", "kyun", "kyon", "kaise", "kitna", "kitni", "kitne", "kaun", "kab", "samajh", "batao", "bataiye",
    "क्या", "क्यों", "क्यूँ", "कैसे", "कितना", "कितनी", "कितने", "कौन", "कब", "समझ", "बताओ", "बताइए", "बताइये",
]


# Gurmukhi, Gujarati and Bengali are laid out like Devanagari in Unicode, a fixed distance away.
# Subtracting that distance turns "ਠੀਕ ਹੈ" (Gurmukhi) into "ठीक है" (Devanagari).
_SISTER_SCRIPTS = ((0x0A00, 0x0A7F, 0x100),    # Gurmukhi (Punjabi)
                   (0x0A80, 0x0AFF, 0x180),    # Gujarati
                   (0x0980, 0x09FF, 0x080))    # Bengali
_SENTENCE_MARKS = "।॥.,!;:…\"“”‘’()[]"         # "?" is kept: it tells us the seller asked a question


def tidy(utterance: str) -> str:
    """Prepare the seller's words for matching: lower case, one script, no sentence marks.

    Returns the text with a space at each end, so whole-word checks work at the edges."""
    out = []
    for ch in utterance.lower():
        code = ord(ch)
        for first, last, distance in _SISTER_SCRIPTS:
            if first <= code <= last:
                ch = chr(code - distance)
                break
        out.append(" " if ch in _SENTENCE_MARKS else ch)
    return " " + " ".join("".join(out).split()) + " "


def _has(text: str, words: list[str]) -> bool:
    """True if any of `words` appears in `text` as a whole word or phrase.

    Whole-word matching matters: "no" must not match inside "know", and "ha" must not
    match inside "that". Latin and Devanagari words need different boundary rules."""
    for w in words:
        if re.search(r"[a-z]", w):
            if re.search(rf"(?<![a-z']){re.escape(w)}(?![a-z'])", text):
                return True
        elif re.search(rf"(?<![ऀ-ॿ]){re.escape(w)}(?![ऀ-ॿ])", text):
            return True
    return False


def is_clear_yes(utterance: str) -> bool:
    """True only when the seller's words clearly agree to what was just proposed."""
    text = tidy(utterance)
    if len(text.strip()) == 0 or _has(text, NO_WORDS):
        return False
    if _has(text, STRONG_YES):
        return True
    if "?" in text or _has(text, QUESTION_WORDS):
        return False
    return _has(text, YES_WORDS)


# ---- which action was the yes about? -------------------------------------------------
# A yes only counts for an action the agent had just proposed (or the seller asked for by name).
# These are the words either side would use for each action, in English, Hindi and Hinglish.
ACTION_WORDS = {
    "restock_plan": ["restock", "re-stock", "replenish", "reorder", "re-order", "stock wapas", "stock bhar", "mangwa",
                     "रीस्टॉक", "रिस्टॉक", "री-स्टॉक", "स्टॉक वापस", "स्टॉक भर", "मंगवा"],
    "pause_listings": ["pause", "switch off", "turn off", "band kar", "rok d", "पॉज", "पॉज़", "बंद कर", "रोक द"],
    "stock_buffer": ["buffer", "safety stock", "बफर", "बफ़र", "सेफ्टी"],
    "price_match": ["price", "pricing", "discount", "daam", "keemat", "sasta", "प्राइस", "दाम", "कीमत", "डिस्काउंट", "सस्ता"],
    "dispatch_alerts": ["dispatch", "alert", "reminder", "pickup", "pick-up", "डिस्पैच", "अलर्ट", "रिमाइंडर", "पिकअप"],
}
REQUEST_WORDS = ["please", "can you", "could you", "i want", "i need", "kripya", "chahiye", "chahta", "chahti",
                 "कृपया", "चाहिए", "चाहता", "चाहती"]


def mentions(text: str, action: str) -> bool:
    """True if `text` talks about this action (uses one of its words)."""
    low = text.lower()
    return any(w in low for w in ACTION_WORDS.get(action, []))


def seller_agreed(seller_text: str, agent_text_before: str, action: str) -> tuple[bool, str]:
    """Did the seller agree to THIS action? Returns (agreed, reason-if-not).

    seller_text        the seller's most recent words
    agent_text_before  what the agent said just before them (its proposal, if it made one)
    action             the action about to be saved, for example "restock_plan"

    The rules, in order:
      1. Any "no" word                                   -> not agreed ("declined")
      2. The seller named the action and asked for it     -> agreed
      3. No clear yes                                     -> not agreed ("no_clear_yes")
      4. A clear yes, but the agent had not just proposed
         this action                                      -> not agreed ("yes_was_about_something_else")
      5. Otherwise                                        -> agreed
    """
    text = tidy(seller_text)
    if not text.strip():
        return False, "nothing_heard"
    if _has(text, NO_WORDS):
        return False, "declined"
    if mentions(seller_text, action):                       # the seller named the action themselves
        asking = "?" in text or _has(text, QUESTION_WORDS)
        if _has(text, STRONG_YES) or is_clear_yes(seller_text) or (_has(text, REQUEST_WORDS) and not asking):
            return True, ""
    if not is_clear_yes(seller_text):
        return False, "no_clear_yes"
    if action in ACTION_WORDS and not mentions(agent_text_before, action):
        return False, "yes_was_about_something_else"
    return True, ""


# ---- the record of what the gate decided, for the call page ------------------------------
# Why an attempt was refused, in words a reviewer can read.
REFUSED_BECAUSE = {
    "declined": "the seller's reply contained a no",
    "no_clear_yes": "the seller's reply was not a clear yes",
    "yes_was_about_something_else": "the seller's yes was to a different question",
    "yes_already_used": "that yes had already been used for other actions",
    "nothing_heard": "the seller had not said anything yet",
}


def gate_report(log: list[tuple[str, str, str]]) -> dict:
    """What the consent gate decided on a call, for the call record.

    log  one entry per time the model said the seller had agreed:
         (action, "agreed" or the reason it was refused, the seller's words that were checked)

    These are facts, not a reading of the transcript. Returns
    {"allowed": how many actions were let through,
     "refused": [{"action", "why", "seller_said"}, ...]}."""
    refused = [{"action": action.replace("_", " "), "why": REFUSED_BECAUSE.get(why, why.replace("_", " ")),
                "seller_said": heard[:160]}
               for action, why, heard in log if why != "agreed"]
    return {"allowed": len(log) - len(refused), "refused": refused}
