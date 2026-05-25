import os
import base64

from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq

load_dotenv()

gemini_key = os.getenv("GEMINI_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")
gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
llm_primary = os.getenv("LLM_PRIMARY", "groq").lower()

gemini_client = genai.Client(api_key=gemini_key) if gemini_key and not gemini_key.startswith("your_") else None
groq_client = Groq(api_key=groq_key) if groq_key and not groq_key.startswith("your_") else None

GEMINI_FREE_MODELS = [gemini_model, "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-flash-001"]
GROQ_FREE_MODELS = [groq_model, "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "qwen/qwen3-32b"]
GROQ_VISION_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct"]


def has_llm_keys() -> bool:
    return bool((gemini_key and not gemini_key.startswith("your_")) or groq_client)


def call_llm(prompt: str, prefer_fast: bool = False, max_tokens: int = 2000) -> str:
    """
    prefer_fast=True uses Groq/Llama first for quick rewriting tasks.
    prefer_fast=False uses LLM_PRIMARY, defaulting to Groq to avoid Gemini free-quota issues.
    """
    use_groq_first = prefer_fast or llm_primary != "gemini"
    primary = _call_groq if use_groq_first else _call_gemini
    fallback = _call_gemini if use_groq_first else _call_groq

    try:
        return primary(prompt, max_tokens)
    except Exception as error:
        print(f"[LLM] Primary failed ({error}), trying fallback...")
        try:
            return fallback(prompt, max_tokens)
        except Exception as fallback_error:
            raise RuntimeError(f"Both LLMs failed. Check Gemini/Groq keys. Error: {fallback_error}") from fallback_error


def extract_text_from_image(image_bytes: bytes, mime_type: str) -> str:
    prompt = (
        "Extract all readable text from this image. Preserve line breaks where useful. "
        "Return only the extracted text, no commentary."
    )

    try:
        return _call_groq_vision(prompt, image_bytes, mime_type)
    except Exception as error:
        print(f"[LLM] Groq vision failed ({error}), trying Gemini vision...")
        return _call_gemini_vision(prompt, image_bytes, mime_type)


def _call_gemini(prompt: str, max_tokens: int) -> str:
    if not gemini_client:
        raise RuntimeError("GEMINI_API_KEY not set")

    last_error: Exception | None = None
    for model in _unique(GEMINI_FREE_MODELS):
        try:
            response = gemini_client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=max_tokens, temperature=0),
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Gemini returned an empty response")
            return text
        except Exception as error:
            last_error = error
            print(f"[LLM] Gemini model failed ({model}): {error}")

    raise RuntimeError(f"All Gemini free models failed: {last_error}")


def _call_gemini_vision(prompt: str, image_bytes: bytes, mime_type: str) -> str:
    if not gemini_client:
        raise RuntimeError("GEMINI_API_KEY not set")

    last_error: Exception | None = None
    for model in _unique(GEMINI_FREE_MODELS):
        try:
            response = gemini_client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(max_output_tokens=2500, temperature=0),
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Gemini vision returned an empty response")
            return text
        except Exception as error:
            last_error = error
            print(f"[LLM] Gemini vision model failed ({model}): {error}")

    raise RuntimeError(f"All Gemini vision models failed: {last_error}")


def _call_groq(prompt: str, max_tokens: int) -> str:
    if not groq_client:
        raise RuntimeError("GROQ_API_KEY not set")

    last_error: Exception | None = None
    for model in _unique(GROQ_FREE_MODELS):
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("Groq returned an empty response")
            return text
        except Exception as error:
            last_error = error
            print(f"[LLM] Groq model failed ({model}): {error}")

    raise RuntimeError(f"All Groq free models failed: {last_error}")


def _call_groq_vision(prompt: str, image_bytes: bytes, mime_type: str) -> str:
    if not groq_client:
        raise RuntimeError("GROQ_API_KEY not set")

    image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    last_error: Exception | None = None
    for model in _unique(GROQ_VISION_MODELS):
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
                max_tokens=2500,
                temperature=0,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("Groq vision returned an empty response")
            return text
        except Exception as error:
            last_error = error
            print(f"[LLM] Groq vision model failed ({model}): {error}")

    raise RuntimeError(f"All Groq vision models failed: {last_error}")


def _unique(models: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model in models:
        if model in seen:
            continue
        seen.add(model)
        result.append(model)
    return result
