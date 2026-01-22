from __future__ import annotations

import os
from typing import Any

import requests

from app.core.errors import ExternalAPIError
from app.core.retry import retryable

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_TIMEOUT = float(os.getenv("QDRANT_TIMEOUT", "10"))


class QdrantError(RuntimeError):
    pass


@retryable("qdrant")
def _request(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> requests.Response:
    url = f"{QDRANT_URL}{path}"
    response = requests.request(method, url, json=json, timeout=timeout)
    if response.status_code == 429 or response.status_code >= 500:
        raise ExternalAPIError(
            "qdrant",
            f"Qdrant error {response.status_code}: {response.text}",
            status_code=response.status_code,
        )
    return response


def create_collection_if_not_exists(
    collection: str,
    vector_size: int,
    distance: str = "Cosine",
) -> None:
    response = _request("GET", f"/collections/{collection}")
    if response.status_code == 200:
        return
    if response.status_code != 404:
        raise QdrantError(
            f"Unexpected status {response.status_code}: {response.text}"
        )
    payload = {"vectors": {"size": vector_size, "distance": distance}}
    create_response = _request(
        "PUT",
        f"/collections/{collection}",
        json=payload,
    )
    if create_response.status_code not in {200, 201}:
        raise QdrantError(
            f"Create collection failed: {create_response.status_code} {create_response.text}"
        )


def upsert_points(collection: str, points: list[dict[str, Any]]) -> None:
    payload = {"points": points}
    response = _request(
        "PUT",
        f"/collections/{collection}/points",
        json=payload,
    )
    if response.status_code not in {200, 201}:
        raise QdrantError(
            f"Upsert failed: {response.status_code} {response.text}"
        )


def search(
    collection: str,
    query_vector: list[float],
    limit: int,
    score_threshold: float | None,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"vector": query_vector, "limit": limit}
    if score_threshold is not None:
        payload["score_threshold"] = score_threshold
    response = _request(
        "POST",
        f"/collections/{collection}/points/search",
        json=payload,
    )
    if response.status_code != 200:
        raise QdrantError(
            f"Search failed: {response.status_code} {response.text}"
        )
    data = response.json()
    return data.get("result", [])
