import json
import os

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-flash-latest"
TIMEOUT = 30


def gemini_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _generate_content(prompt: str, generation_config: dict | None = None) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Gemini isn't configured.")

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    url = f"{API_BASE}/{model}:generateContent"

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if generation_config:
        body["generationConfig"] = generation_config

    try:
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except requests.RequestException as exc:
        raise RuntimeError(f"Couldn't reach Gemini: {exc}") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError("Gemini returned an unexpected response.") from exc


def ask_gemini(prompt: str) -> str:
    """Send a single-turn prompt to the Gemini API and return the reply text.
    Raises RuntimeError on any failure (missing key, network error, bad
    response shape) with a message safe to show the user."""
    return _generate_content(prompt)


def ask_gemini_json(prompt: str, schema: dict) -> dict:
    """Like ask_gemini, but constrains the response to JSON matching `schema`
    (Gemini's OpenAPI-subset schema format: {"type": "OBJECT", "properties": {...}})
    and returns it already parsed. Raises RuntimeError on failure, including
    if Gemini's output doesn't parse as JSON."""
    text = _generate_content(
        prompt,
        generation_config={"responseMimeType": "application/json", "responseSchema": schema},
    )
    try:
        return json.loads(text)
    except ValueError as exc:
        raise RuntimeError("Gemini returned invalid JSON.") from exc
