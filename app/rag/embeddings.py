from __future__ import annotations

from typing import Iterable

from sentence_transformers import SentenceTransformer

_MODEL: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MODEL


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    model = _get_model()
    return model.encode(list(texts), normalize_embeddings=True).tolist()


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
