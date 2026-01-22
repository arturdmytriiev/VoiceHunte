from __future__ import annotations

from typing import Any

from app.rag.embeddings import embed_text
from app.rag.qdrant_repo import search

DEFAULT_COLLECTION = "menu"
DEFAULT_SCORE_THRESHOLD = 0.2


def retrieve_menu_context(
    query: str,
    lang: str,
    top_k: int = 5,
    collection: str = DEFAULT_COLLECTION,
) -> list[dict[str, Any]]:
    _ = lang
    query_vector = embed_text(query)
    results = search(
        collection=collection,
        query_vector=query_vector,
        limit=top_k,
        score_threshold=DEFAULT_SCORE_THRESHOLD,
    )
    normalized: list[dict[str, Any]] = []
    for result in results:
        payload = result.get("payload", {})
        normalized.append(
            {
                "name": payload.get("name"),
                "description": payload.get("description"),
                "price": payload.get("price"),
                "category": payload.get("category"),
            }
        )
    return normalized
