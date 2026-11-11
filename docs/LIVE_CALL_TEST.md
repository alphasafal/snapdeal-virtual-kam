# Live call test, 11 November 2026

One full call against the real services (LiveKit, the Sarvam language model and Sarvam
text-to-speech), run on a laptop after the fixes from the Hindi call of 10 November.

**How it was run.** The seller's side was typed, using the call screen's typing mode, in the
exact form speech-to-text produces (Devanagari with English business words, sentences ending
in "।"). Asha answered aloud as usual. So this test covers the language model, the tools, the
consent check, the call record and the hang-up. It does not cover speech-to-text or
turn-taking, and reply delay was not measured.

## Result

| What was checked | Expected | Observed |
|---|---|---|
| Call set-up | A few seconds | 1.4 to 2.5 seconds across the three calls made that night (almost all of it joining the room) |
| Diagnosis | The drop, the main cause with a rupee figure, one question | Two lakh to one lakh thirty-five thousand, about forty-five thousand from stockouts, cancellations named as the second cause, then one question |
| Seller's reason is recorded | Saved before any proposal | "Noted what the seller explained" |
| Proposal is a question | "Shall I ...?", not "I am doing ..." | "तो क्या मैं आपके top five products का एक restock plan बना दूँ?" |
| A question instead of a yes ("इससे क्या फायदा होगा?") | Answered; nothing saved | Answered; nothing saved |
| "जी बना दीजिए।" (refused on 10 November) | Restock plan saved first time | Saved first time |
| "कर दीजिए।" (refused twice on 10 November) | Listings paused first time | Saved first time |
| A clear no ("नहीं, वो रहने दीजिए।") | Nothing saved, no repeat of the question | Nothing saved; she moved on |
| Follow-up | A date is booked and spoken | 18 November |
| Summary | Issue, actions with deadline, follow-up | Given |
| Goodbye and hang-up | Full goodbye, then she ends the call | "ठीक है राजेश जी, धन्यवाद। अपना ध्यान रखिएगा।", then the call ended |
| Figure check | Every rupee amount spoken matches the data | 6 figures checked, none flagged |
| Cost | About ₹1.4 to ₹1.8 a minute | ₹5.65 for 4 minutes 22 seconds, about ₹1.30 a minute (no speech-to-text in this test) |

## What it found, and what changed

1. **After the seller said "that is enough", Asha asked one more question** whose answer was
   already in the data. The instructions now say: when the seller wants to stop, propose and
   ask nothing more; book the follow-up and give the summary.
2. **"Ended the call" appeared twice in the transcript.** The screens now show a repeated step once.
3. **Her replies run long** (several sentences where the instructions ask for two). This is
   unchanged; it is the model's habit, and it makes a full call about four minutes.

## The conversation

| Speaker | Words |
|---|---|
| Asha | नमस्ते राजेश जी, मैं Snapdeal से आशा बोल रही हूँ। बताइए, आज मैं आपकी क्या help कर सकती हूँ? |
| Seller | मेरी sales इस महीने बहुत गिर गई हैं। क्यों? |
| Asha | समझ सकती हूँ, ये परेशान करने वाला है। मैंने आपका account check किया है। आपकी sales पिछले महीने के two lakh rupees से इस महीने one lakh thirty-five thousand rupees हो गई हैं, मतलब करीब thirty two percent की गिरावट। इसका सबसे बड़ा reason ये है कि आपके products बार-बार stock से बाहर हो रहे हैं, जिसकी वजह से करीब forty five thousand rupees का नुकसान हुआ है। इसके अलावा cancellations भी बढ़ गए हैं। क्या आप बता सकते हैं कि stock बार-बार खत्म क्यों हो रहा है? |
| Seller | Supplier ने delivery late कर दी थी। |
| Asha | ठीक है, noted. Supplier delay की वजह से ही ये problem आई है। तो क्या मैं आपके top five products का एक restock plan बना दूँ? इससे करीब twenty five thousand rupees की sales recover हो सकती है। |
| Seller | इससे क्या फायदा होगा? |
| Asha | देखिए, आपके top five products ने इस महीने करीब twenty five thousand rupees का loss किया है। अगर हम इन्हें restock कर देंगे, तो जो orders अभी stock out की वजह से miss हो रहे हैं, वो वापस आ जाएंगे। क्या मैं plan बना दूँ? |
| Seller | जी बना दीजिए। |
| Asha | हो गया, restock plan बन गया है। इसमें आपके top five products हैं, और ये 14 November तक ready हो जाएंगे। अब जो products supplier के पास फँसे हैं, उन्हें pause कर दें ताकि cancellations ना बढ़ें? |
| Seller | कर दीजिए। |
| Asha | हो गया, 13 out-of-stock listings pause कर दी गई हैं। अब क्या हम एक safety buffer set कर लें? |
| Seller | नहीं, वो रहने दीजिए। बस इतना काफ़ी है। |
| Asha | ठीक है, buffer अभी नहीं set करते हैं। (then one more question; see finding 1) |
| Seller | बस, और कुछ नहीं चाहिए। |
| Asha | ठीक है, तो आपकी sales stock out की वजह से गिरी हैं, और हमने top five products का restock plan बना दिया है जो 14 November तक ready हो जाएगा। साथ ही 13 out-of-stock listings भी pause कर दी गई हैं। क्या मैं अगले हफ्ते के लिए एक follow-up call schedule कर दूँ? |
| Seller | हाँ, अगले हफ्ते कर दीजिए। |
| Asha | ठीक है, follow-up call 18 November, Wednesday को schedule कर दी है। क्या और कोई help चाहिए? |
| Seller | नहीं, बस। धन्यवाद। |
| Asha | ठीक है राजेश जी, धन्यवाद। अपना ध्यान रखिएगा। |
