from __future__ import annotations

from typing import Iterator

import requests

from app.core.config import settings
from app.core.errors import ExternalAPIError
from app.core.retry import retryable

OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
DEFAULT_MODEL = "tts-1"
DEFAULT_VOICE = "alloy"
SUPPORTED_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
SUPPORTED_MODELS = {"tts-1", "tts-1-hd"}
SUPPORTED_FORMATS = {"mp3", "opus", "aac", "flac", "wav", "pcm"}


def stream_tts(
    text: str,
    *,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    response_format: str = "mp3",
    speed: float = 1.0,
) -> Iterator[bytes]:
    """
    Stream audio from OpenAI TTS API.

    Args:
        text: Text to convert to speech
        voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
        model: Model to use (tts-1, tts-1-hd)
        response_format: Audio format (mp3, opus, aac, flac, wav, pcm)
        speed: Speech speed (0.25 to 4.0)

    Yields:
        Audio chunks as bytes
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    if voice not in SUPPORTED_VOICES:
        raise ValueError(f"Unsupported voice: {voice}. Must be one of {SUPPORTED_VOICES}")

    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model: {model}. Must be one of {SUPPORTED_MODELS}")

    if response_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {response_format}. Must be one of {SUPPORTED_FORMATS}")

    if not 0.25 <= speed <= 4.0:
        raise ValueError(f"Speed must be between 0.25 and 4.0, got {speed}")

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": response_format,
        "speed": speed,
    }

    with _post_tts_request(headers=headers, payload=payload) as response:
        response.raise_for_status()

        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                yield chunk


@retryable("openai_tts")
def _post_tts_request(
    *,
    headers: dict[str, str],
    payload: dict[str, object],
) -> requests.Response:
    response = requests.post(
        OPENAI_TTS_URL,
        headers=headers,
        json=payload,
        stream=True,
        timeout=60,
    )
    if response.status_code == 429 or response.status_code >= 500:
        raise ExternalAPIError(
            "openai_tts",
            f"OpenAI TTS error {response.status_code}: {response.text}",
            status_code=response.status_code,
        )
    return response


def tts_to_file(
    text: str,
    output_path: str,
    *,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    response_format: str = "mp3",
    speed: float = 1.0,
) -> None:
    """
    Generate TTS audio and save to file.

    Args:
        text: Text to convert to speech
        output_path: Path to save audio file
        voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
        model: Model to use (tts-1, tts-1-hd)
        response_format: Audio format (mp3, opus, aac, flac, wav, pcm)
        speed: Speech speed (0.25 to 4.0)
    """
    with open(output_path, "wb") as f:
        for chunk in stream_tts(
            text,
            voice=voice,
            model=model,
            response_format=response_format,
            speed=speed,
        ):
            f.write(chunk)
