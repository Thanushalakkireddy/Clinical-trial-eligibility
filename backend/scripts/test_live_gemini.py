"""Manual connectivity test utility for Gemini LLM service.

Usage:
    python backend/scripts/test_live_gemini.py

Requires GEMINI_API_KEY to be set in environment.
Does NOT send any patient data or clinical data.
"""

import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.llm.gemini_service import GeminiLLMService


async def main() -> None:
    api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        print("Gemini API key not configured; live LLM test skipped.")
        return

    print(f"Connecting to Gemini with model: {settings.gemini_model}...")
    service = GeminiLLMService()

    try:
        response = await service.generate(
            prompt="Respond with exactly: GEMINI_CONNECTION_OK",
            temperature=0.0,
        )
        print(f"Live Gemini API Response: {response}")
    except Exception as e:
        print(f"Live Gemini API test failed with error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
