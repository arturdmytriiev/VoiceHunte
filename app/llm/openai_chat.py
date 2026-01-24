from __future__ import annotations

import requests
import structlog

from app.core.config import settings
from app.core.errors import ExternalAPIError
from app.core.retry import retryable

logger = structlog.get_logger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


@retryable("openai_chat")
def _post_chat_request(
    *,
    headers: dict[str, str],
    payload: dict[str, object],
) -> requests.Response:
    response = requests.post(
        OPENAI_CHAT_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    if response.status_code == 429 or response.status_code >= 500:
        raise ExternalAPIError(
            "openai_chat",
            f"OpenAI Chat error {response.status_code}: {response.text}",
            status_code=response.status_code,
        )
    return response


def chat_completion(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> str:
    """
    Send a chat completion request to OpenAI API.

    Args:
        prompt: The user prompt to send
        model: Model to use (default: from settings.llm_intent_model)
        temperature: Sampling temperature (0.0 for deterministic output)
        max_tokens: Maximum tokens in response

    Returns:
        The assistant's response text

    Raises:
        RuntimeError: If OpenAI API key is not configured
        ExternalAPIError: If the API request fails
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    model = model or settings.llm_intent_model

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    logger.debug("openai_chat_request", model=model, prompt_length=len(prompt))

    response = _post_chat_request(headers=headers, payload=payload)
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    logger.debug("openai_chat_response", response_length=len(content))

    return content
