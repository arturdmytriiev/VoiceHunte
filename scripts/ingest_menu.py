from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.rag.embeddings import embed_texts
from app.rag.menu_models import MenuItem
from app.rag.qdrant_repo import create_collection_if_not_exists, upsert_points

DEFAULT_COLLECTION = "menu"
DEFAULT_MENU_PATH = Path("data/menu.json")


def _load_menu(path: Path) -> list[MenuItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [MenuItem.model_validate(item) for item in data]


def _item_to_text(item: MenuItem) -> str:
    tags = ", ".join(item.tags or [])
    allergens = ", ".join(item.allergens or [])
    parts = [
        item.name,
        item.description,
        f"Category: {item.category}",
        f"Price: {item.price}",
    ]
    if tags:
        parts.append(f"Tags: {tags}")
    if allergens:
        parts.append(f"Allergens: {allergens}")
    return ". ".join(parts)


def ingest_menu(
    collection: str = DEFAULT_COLLECTION,
    menu_path: Path = DEFAULT_MENU_PATH,
) -> None:
    items = _load_menu(menu_path)
    texts = [_item_to_text(item) for item in items]
    vectors = embed_texts(texts)
    create_collection_if_not_exists(collection, vector_size=len(vectors[0]))
    points = [
        {
            "id": str(uuid.uuid4()),
            "vector": vector,
            "payload": item.model_dump(),
        }
        for item, vector in zip(items, vectors, strict=True)
    ]
    upsert_points(collection, points)


if __name__ == "__main__":
    ingest_menu()
