from __future__ import annotations

from psycopg.rows import dict_row
from fastapi.testclient import TestClient

from app import main
from app.db.conversations import ConversationStore


def test_mvp_text_creates_reservation_and_turn(clean_db, postgres_dsn: str) -> None:
    main.store = ConversationStore(postgres_dsn)
    client = TestClient(main.app)
    payload = {
        "text": "Создай бронь на 05.06.2025 в 19:30 на 3 человека, меня зовут Иван.",
        "language": "ru",
        "call_id": "test-call",
    }

    response = client.post("/mvp/text", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["reservation_id"] is not None

    with clean_db.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM reservations")
        reservation = cur.fetchone()
        assert reservation is not None
        assert reservation["name"] == "Иван"
        assert reservation["people"] == 3

        cur.execute("SELECT * FROM turns WHERE call_id = %s", ("test-call",))
        turn = cur.fetchone()
        assert turn is not None
        assert turn["user_text"] == payload["text"]
