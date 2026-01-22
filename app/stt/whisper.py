from __future__ import annotations

import math
import re
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests

from app.core.config import settings
from app.core.errors import ExternalAPIError
from app.core.retry import retryable

SUPPORTED_LANGUAGES = {"sk", "en", "ru", "uk"}
SUPPORTED_MODES = {"transcribe", "translate"}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
OPENAI_API_BASE = "https://api.openai.com/v1/audio"
WHISPER_MODEL = "whisper-1"


@dataclass(slots=True)
class STTResult:
    text: str
    language: str
    segments: list[dict[str, Any]] | None = None
    confidence: float | None = None
    duration: float | None = None


def transcribe(
    audio_path: str | Path,
    language: str,
    mode: str,
) -> STTResult:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")

    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    combined_text: list[str] = []
    combined_segments: list[dict[str, Any]] | None = []
    detected_language = language
    total_duration: float | None = 0.0

    for chunk in _split_audio(audio_path):
        response = _request_whisper(chunk, language=language, mode=mode, api_key=api_key)
        combined_text.append(response.text)

        if response.language:
            detected_language = response.language

        if response.segments is None:
            combined_segments = None
        elif combined_segments is not None:
            combined_segments.extend(response.segments)

        if response.duration is None:
            total_duration = None
        elif total_duration is not None:
            total_duration += response.duration

    normalized_text = _normalize_text(" ".join(combined_text))

    return STTResult(
        text=normalized_text,
        language=detected_language,
        segments=combined_segments,
        confidence=_merge_confidence(combined_segments),
        duration=total_duration,
    )


def _request_whisper(
    audio_path: Path,
    *,
    language: str,
    mode: str,
    api_key: str,
) -> STTResult:
    endpoint = "transcriptions" if mode == "transcribe" else "translations"
    response_format = "verbose_json" if mode == "transcribe" else "json"

    response = _post_whisper_request(
        audio_path=audio_path,
        endpoint=endpoint,
        response_format=response_format,
        language=language,
        api_key=api_key,
    )

    if response.ok:
        payload = response.json()
        return _parse_response(payload, fallback_language=language)

    if response.status_code == 400:
        fallback_response = _post_whisper_request(
            audio_path=audio_path,
            endpoint=endpoint,
            response_format=response_format,
            language=None,
            api_key=api_key,
        )
        if fallback_response.ok:
            payload = fallback_response.json()
            return _parse_response(payload, fallback_language=language)

    response.raise_for_status()
    raise RuntimeError("Failed to call Whisper API")


@retryable("openai_stt")
def _post_whisper_request(
    *,
    audio_path: Path,
    endpoint: str,
    response_format: str,
    language: str | None,
    api_key: str,
) -> requests.Response:
    with audio_path.open("rb") as audio_file:
        files = {
            "file": (audio_path.name, audio_file, "application/octet-stream"),
        }
        data = {
            "model": WHISPER_MODEL,
            "response_format": response_format,
        }
        if language is not None:
            data["language"] = language
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        response = requests.post(
            f"{OPENAI_API_BASE}/{endpoint}",
            headers=headers,
            data=data,
            files=files,
            timeout=120,
        )

    if response.status_code == 429 or response.status_code >= 500:
        raise ExternalAPIError(
            "openai_stt",
            f"OpenAI STT error {response.status_code}: {response.text}",
            status_code=response.status_code,
        )
    return response


def _parse_response(payload: dict[str, Any], *, fallback_language: str) -> STTResult:
    text = _normalize_text(payload.get("text", ""))
    language = payload.get("language") or fallback_language
    segments = payload.get("segments")
    duration = payload.get("duration")
    confidence = payload.get("confidence")

    return STTResult(
        text=text,
        language=language,
        segments=segments,
        confidence=confidence,
        duration=duration,
    )


def _normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\u200b\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_audio(audio_path: Path) -> Iterable[Path]:
    if audio_path.stat().st_size <= MAX_FILE_SIZE_BYTES:
        yield audio_path
        return

    if audio_path.suffix.lower() == ".wav":
        yield from _split_wav(audio_path)
        return

    yield from _split_binary(audio_path)


def _split_wav(audio_path: Path) -> Iterable[Path]:
    with wave.open(str(audio_path), "rb") as wav:
        frame_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        bytes_per_frame = channels * sample_width
        max_frames = max(1, MAX_FILE_SIZE_BYTES // bytes_per_frame)
        total_frames = wav.getnframes()
        chunks = math.ceil(total_frames / max_frames)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            for index in range(chunks):
                chunk_path = temp_dir_path / f"chunk_{index}.wav"
                with wave.open(str(chunk_path), "wb") as chunk_wav:
                    chunk_wav.setnchannels(channels)
                    chunk_wav.setsampwidth(sample_width)
                    chunk_wav.setframerate(frame_rate)
                    frames = wav.readframes(max_frames)
                    if not frames:
                        break
                    chunk_wav.writeframes(frames)
                yield chunk_path


def _split_binary(audio_path: Path) -> Iterable[Path]:
    suffix = audio_path.suffix or ".chunk"
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        with audio_path.open("rb") as source:
            index = 0
            while True:
                chunk = source.read(MAX_FILE_SIZE_BYTES)
                if not chunk:
                    break
                chunk_path = temp_dir_path / f"chunk_{index}{suffix}"
                chunk_path.write_bytes(chunk)
                yield chunk_path
                index += 1


def _merge_confidence(segments: list[dict[str, Any]] | None) -> float | None:
    if segments is None or not segments:
        return None
    avg_logprobs: list[float] = []
    for segment in segments:
        value = segment.get("avg_logprob")
        if isinstance(value, (int, float)):
            avg_logprobs.append(float(value))
    if not avg_logprobs:
        return None
    return float(sum(avg_logprobs) / len(avg_logprobs))
