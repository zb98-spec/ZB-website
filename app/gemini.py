import os

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-flash-latest"
TIMEOUT = 30


def gemini_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def ask_gemini(prompt: str) -> str:
    """Send a single-turn prompt to the Gemini API and return the reply text.
    Raises RuntimeError on any failure (missing key, network error, bad
    response shape) with a message safe to show the user."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Gemini isn't configured.")

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    url = f"{API_BASE}/{model}:generateContent"

    try:
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except requests.RequestException as exc:
        raise RuntimeError(f"Couldn't reach Gemini: {exc}") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError("Gemini returned an unexpected response.") from exc
