from __future__ import annotations

from typing import Any

from app.rag import qdrant_repo


class DummyResponse:
    def __init__(
        self, status_code: int, json_data: dict[str, Any] | None = None, text: str = ""
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._json_data


def test_qdrant_wrapper_create_upsert_search(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(method: str, url: str, json: dict[str, Any] | None, timeout: float):
        calls.append((method, url, json))
        if method == "GET":
            return DummyResponse(404)
        if method == "PUT" and url.endswith("/collections/test_collection"):
            return DummyResponse(201)
        if method == "PUT" and url.endswith("/points"):
            return DummyResponse(200)
        if method == "POST":
            return DummyResponse(200, {"result": [{"id": 1, "score": 0.91}]})
        raise AssertionError(f"Unexpected call {method} {url}")

    monkeypatch.setattr(qdrant_repo, "QDRANT_URL", "http://qdrant")
    monkeypatch.setattr(qdrant_repo.requests, "request", fake_request)

    qdrant_repo.create_collection_if_not_exists(
        "test_collection", vector_size=3, distance="Cosine"
    )
    qdrant_repo.upsert_points(
        "test_collection",
        [
            {"id": 1, "vector": [0.1, 0.2, 0.3], "payload": {"title": "Soup"}},
        ],
    )
    results = qdrant_repo.search(
        "test_collection",
        [0.1, 0.2, 0.3],
        limit=1,
        score_threshold=0.5,
    )

    assert results == [{"id": 1, "score": 0.91}]
    assert calls[0][0] == "GET"
    assert calls[1][0] == "PUT"
    assert calls[1][2] == {"vectors": {"size": 3, "distance": "Cosine"}}
    assert calls[2][0] == "PUT"
    assert calls[3][0] == "POST"
