"""First Sarvam call: text to speech. Saves hello_sarvam.wav next to this file.

Run:  python hello_sarvam.py
"""
import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from sarvamai import SarvamAI

load_dotenv()
client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])

response = client.text_to_speech.convert(
    text="Namaste Rajesh ji, this is Asha from Snapdeal. I noticed your orders dropped this month. "
         "Do you have two minutes to fix it together?",
    language_code="en-IN",
    model="bulbul:v3",
    output_audio_codec="wav",
)

out = Path(__file__).with_name("hello_sarvam.wav")
out.write_bytes(base64.b64decode("".join(response.audios)))
print(f"Saved {out.name} ({out.stat().st_size:,} bytes)")
