"""Checks the rupee figures the agent spoke against the figures it was given.

The prompt forbids invented numbers, but nothing in a language model guarantees it. After
every call this module reads what the agent said, extracts each rupee-scale amount (digits,
English words, Hindi words in Devanagari, and common Roman Hindi), and compares it with
the amounts in the account brief and in the tool results. Anything that matches nothing is
listed on the call record for a person to look at.

Limits, stated plainly: it checks amounts of 1,000 and above, not counts or percentages;
it cannot tell whether a correct figure was used with the wrong meaning; and a Roman Hindi
number word it does not know makes it skip that phrase rather than guess.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

MULTIPLIERS = {
    "thousand": 1e3, "thousands": 1e3, "hazaar": 1e3, "hazar": 1e3, "hajar": 1e3, "hajaar": 1e3, "हज़ार": 1e3, "हजार": 1e3,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "लाख": 1e5,
    "million": 1e6, "crore": 1e7, "crores": 1e7, "करोड़": 1e7, "करोड": 1e7,
}
HUNDREDS = {"hundred", "sau", "सौ"}

ENGLISH = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
ENGLISH.update({"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                "eighty": 80, "ninety": 90})

_DEV = ("एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस "
        "इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस "
        "सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास "
        "इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ "
        "अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी अस्सी इक्यासी बयासी "
        "तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे "
        "सत्तानवे अट्ठानवे निन्यानवे").split()
DEVANAGARI = {w: i + 1 for i, w in enumerate(_DEV)}
DEVANAGARI.update({"पांच": 5, "छः": 6, "छे": 6, "डेढ़": 1.5, "ढाई": 2.5, "पन्द्रह": 15, "अठ्ठारह": 18})

# Roman Hindi spellings vary; this covers the common ones. An unknown word is skipped, never guessed.
ROMAN = {
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6,
    "chhah": 6, "chah": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12,
    "baarah": 12, "terah": 13, "chaudah": 14, "pandrah": 15, "solah": 16, "satrah": 17, "satraah": 17, "atharah": 18,
    "athara": 18, "atthara": 18, "unnis": 19, "unnees": 19, "bees": 20, "bis": 20, "pachees": 25, "pachis": 25,
    "pacchis": 25, "tees": 30, "tis": 30, "paintees": 35, "paintis": 35, "paithis": 35, "paitis": 35, "painthis": 35,
    "chalis": 40, "chaalis": 40, "chalees": 40, "paintalis": 45, "paintaalis": 45, "paintalees": 45, "pentalis": 45,
    "pachas": 50, "pachaas": 50, "pachpan": 55, "saath": 60, "sath": 60, "painsath": 65, "sattar": 70,
    "pachattar": 75, "assi": 80, "pachasi": 85, "nabbe": 90, "pachanve": 95, "dedh": 1.5, "dhai": 2.5,
}

_TOKEN = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)?|[a-z]+|[\u0900-\u097F]+")


def _kind(tok: str):
    """('digit'|'unit'|'roman'|'hundred'|'mult', value) for a number token, else None."""
    if tok[0].isdigit():
        try:
            return "digit", float(tok.replace(",", ""))
        except ValueError:
            return None
    if tok in MULTIPLIERS:
        return "mult", MULTIPLIERS[tok]
    if tok in HUNDREDS:
        return "hundred", 100
    if tok in ENGLISH:
        return "unit", ENGLISH[tok]
    if tok in DEVANAGARI:
        return "unit", DEVANAGARI[tok]
    if tok in ROMAN:
        return "roman", ROMAN[tok]
    return None


def amounts(text: str) -> list[tuple[float, str]]:
    """Rupee-scale amounts in `text` as (value, phrase). Only values of 1,000 and above."""
    # Punctuation between two tokens ends a number: "₹65,000 (32.5%): ₹2,00,000" is three figures.
    toks, last_end, low = [], 0, text.lower()
    for m in _TOKEN.finditer(low):
        if toks and low[last_end:m.start()].strip(" -,\u00a0"):
            toks.append("|")
        toks.append(m.group())
        last_end = m.end()
    kinds = [None if t == "|" else _kind(t) for t in toks]
    out: list[tuple[float, str]] = []
    i, n = 0, len(toks)
    while i < n:
        k = kinds[i]
        nxt = kinds[i + 1] if i + 1 < n else None
        # a Roman Hindi unit counts only when a multiplier follows it ("do lakh"), because many
        # of these are ordinary English words too ("do", "so", "teen", "saath")
        if k is None or (k[0] == "roman" and not (nxt and nxt[0] in ("mult", "hundred"))) or k[0] in ("mult", "hundred"):
            i += 1
            continue
        total, current, j, has_scale = 0.0, 0.0, i, False
        while j < n:
            kj = kinds[j]
            if kj is None and toks[j] == "and" and j + 1 < n and kinds[j + 1] and kinds[j + 1][0] in ("unit", "digit"):
                j += 1
                continue
            if kj is None:
                break
            kind, val = kj
            if kind == "roman":
                after = kinds[j + 1] if j + 1 < n else None
                if not (after and after[0] in ("mult", "hundred")):
                    break
            if kind == "digit" and j > i and kinds[j - 1] and kinds[j - 1][0] == "digit":
                break                                  # two separate figures side by side
            if kind in ("digit", "unit", "roman"):
                current += val
                if kind == "digit" and val >= 1000:
                    has_scale = True
            elif kind == "hundred":
                current = (current or 1) * 100
            else:
                total += (current or 1) * val
                current = 0.0
                has_scale = True
            j += 1
        value = total + current
        # "ek lakh <unknown word> thousand": the number was cut short by a word we do not know
        cut_short = j + 1 < n and kinds[j] is None and kinds[j + 1] and kinds[j + 1][0] == "mult"
        phrase = " ".join(t for t in toks[i:j] if t != "|")
        year_like = len(toks[i:j]) == 1 and "," not in toks[i] and 1900 <= value <= 2100
        if has_scale and value >= 1000 and not cut_short and not year_like:
            out.append((value, phrase))
        i = max(j, i + 1) + (2 if cut_short else 0)
    return out


def allowed_amounts(sources: Iterable[str]) -> list[float]:
    """Every rupee amount found in the texts the agent was given (the brief, tool results)."""
    return sorted({v for text in sources for v, _ in amounts(text or "")})


def audit_call(agent_turns: Iterable[str], sources: Iterable[str], tolerance: float = 0.06) -> dict[str, Any]:
    """Compare every amount the agent spoke with the amounts it was given.

    agent_turns  everything the agent said on the call
    sources      the account brief and every tool result
    tolerance    how far a spoken figure may be from a given one and still match. 6% allows
                 natural rounding ("about 45 thousand" for ₹45,450) but not a wrong figure.

    Returns {"figures_checked": how many amounts were spoken,
             "flags": [{"said": the words, "value": the amount, "in": the sentence}, ...]}.
    """
    allowed = allowed_amounts(sources)
    checked, flags, seen = 0, [], set()
    for turn in agent_turns:
        for value, phrase in amounts(turn):
            checked += 1
            ok = any(abs(value - a) <= tolerance * a for a in allowed)
            if not ok and value not in seen:
                seen.add(value)
                flags.append({"said": phrase, "value": int(value), "in": turn[:200]})
    return {"figures_checked": checked, "flags": flags}
