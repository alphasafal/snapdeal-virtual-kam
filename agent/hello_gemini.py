"""Checks the Google key end to end: which live audio model the agent will use, and
whether the live audio endpoint accepts a connection.

Run:  python hello_gemini.py
"""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from agent import choose_gemini_model, list_gemini_live_models, probe_gemini_live  # noqa: E402


async def main() -> None:
    """Print what this key can do, using the same checks the agent runs before a Gemini call."""
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        raise SystemExit("GOOGLE_API_KEY is empty in agent/.env")
    models = await list_gemini_live_models(key)
    print("Live audio models on this key:", ", ".join(models) or "none")
    model = choose_gemini_model(models, os.environ.get("GEMINI_LIVE_MODEL", "").strip())
    version = await probe_gemini_live(key)
    print("Model the agent will use:", model or "none")
    print("Live endpoint that accepts this key:", version or "none")
    print("RESULT:", "Gemini Live is ready." if model and version else "Not usable; calls will fall back to Sarvam.")


asyncio.run(main())
