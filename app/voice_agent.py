from __future__ import annotations

import os

import requests
from dotenv import load_dotenv


load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")


def text_to_speech(text: str, voice_id: str = DEFAULT_VOICE_ID) -> bytes:
    api_key = (ELEVENLABS_API_KEY or "").strip()
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text[:500],
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }
    response = requests.post(url, headers=headers, json=payload, timeout=45)
    if response.status_code != 200:
        raise RuntimeError(f"ElevenLabs error: {response.text}")
    return response.content
