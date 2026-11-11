"""The number check, using lines Asha actually said on real calls."""
import pytest
from brain.audit import amounts, audit_call

BRIEF = ("Sales: ₹2,00,000 last month -> ₹1,35,000 this month. Sales fell ₹65,000 (32.5%). "
         "Cause 1: stockouts ₹45,450. Cause 2: ₹19,550. Cancellations worth ₹18,900, ₹8,100 more than last month. "
         "Restock the top 5 products; they lost ₹25,300 this month.")


@pytest.mark.parametrize("text,expected", [
    ("Your sales this month are one lakh thirty-five thousand rupees.", [135000]),
    ("Your sales dropped from two lakh rupees to one lakh thirty-five thousand rupees due to stock-outs.", [200000, 135000]),
    ("That should recover up to about thirty-two thousand rupees per month.", [32000]),
    ("आपकी sales पिछले महीने दो लाख से गिरकर इस महीने एक लाख पैंतीस हज़ार हो गई हैं", [200000, 135000]),
    ("इससे आपको करीब 45 हज़ार का नुकसान हुआ", [45000]),
    ("aapki sales chhe lakh rupaye se girkar ek lakh paithis thousand rupaye ho gayi hain", [600000, 135000]),
    ("lagbhag paintaalis thousand rupaye ka nuksan hua hai", [45000]),
    ("Sales fell ₹65,000 (32.5%): ₹2,00,000 to ₹1,35,000, with 130 fewer orders.", [65000, 200000, 135000]),
    ("about 1.35 lakh rupees", [135000]),
    ("forty five thousand four hundred and fifty rupees", [45450]),
    ("I can do that. Kar do. So we restock the top five products by 2026.", []),      # no amounts here
    ("thirteen products ran out and 38 orders were cancelled, about 14 percent", []),  # counts, not rupees
])
def test_amounts_are_read_correctly(text, expected):
    assert [int(v) for v, _ in amounts(text)] == expected


def test_real_call_slip_is_flagged_and_correct_figures_pass():
    said = ["Rajesh ji, aapki sales chhe lakh rupaye se girkar ek lakh paithis thousand rupaye ho gayi hain.",
            "Steel Tiffin Box jaise products ki wajah se lagbhag paintaalis thousand rupaye ka nuksan hua hai.",
            "Your sales dropped from two lakh rupees to one lakh thirty-five thousand rupees."]
    result = audit_call(said, [BRIEF])
    assert result["figures_checked"] == 5
    assert [f["value"] for f in result["flags"]] == [600000]          # "chhe lakh" was never in the data
    assert "chhe lakh" in result["flags"][0]["said"]


def test_rounded_speech_is_not_a_false_alarm():
    said = ["Stockouts cost you about forty-five thousand rupees and cancellations about twenty thousand.",
            "Cancelled orders are worth about nineteen thousand rupees."]
    assert audit_call(said, [BRIEF])["flags"] == []


def test_unknown_roman_number_word_is_skipped_not_guessed():
    assert amounts("ek lakh pachhattarwala thousand rupaye") == []      # unknown word in the middle
