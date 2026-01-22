"""Tests for call session and history functionality."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.conversations import ConversationStore


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def store(clean_db):
    """ConversationStore fixture with clean database."""
    return ConversationStore(pool=clean_db)


def test_update_call_session(store):
    """Test updating call session metadata."""
    # Create initial call
    store.create_turn(
        call_id="CA_SESSION_1",
        language="en",
        user_text="Hello",
        intent="generic",
        tool_calls=None,
        assistant_text="Hi!",
    )

    # Update session
    store.update_call_session(
        call_id="CA_SESSION_1",
        from_number="+1234567890",
        to_number="+0987654321",
        status="in-progress",
    )

    # Verify update
    session = store.get_call_session("CA_SESSION_1")
    assert session is not None
    assert session["from_number"] == "+1234567890"
    assert session["to_number"] == "+0987654321"
    assert session["status"] == "in-progress"


def test_get_call_session_with_turns(store):
    """Test retrieving complete call session with all turns."""
    call_id = "CA_MULTI_TURN"

    # Create multiple turns
    for i in range(3):
        store.create_turn(
            call_id=call_id,
            language="en",
            user_text=f"User message {i}",
            intent="generic",
            tool_calls=[{"tool": "test", "result": "ok"}],
            assistant_text=f"Assistant response {i}",
            turn_id=i + 1,
        )

    # Get complete session
    session = store.get_call_session(call_id)
    assert session is not None
    assert session["call_id"] == call_id
    assert len(session["turns"]) == 3

    # Verify turns are ordered
    for i, turn in enumerate(session["turns"]):
        assert turn["turn_id"] == i + 1
        assert turn["user_text"] == f"User message {i}"
        assert turn["assistant_text"] == f"Assistant response {i}"

    # Verify transcript
    assert "User: User message 0" in session["transcript"]
    assert "Assistant: Assistant response 0" in session["transcript"]


def test_list_call_sessions(store):
    """Test listing call sessions with pagination."""
    # Create multiple calls
    for i in range(5):
        store.create_turn(
            call_id=f"CA_LIST_{i}",
            language="en",
            user_text="Test",
            intent="generic",
            tool_calls=None,
            assistant_text="Response",
        )

    # List all calls
    sessions = store.list_call_sessions(limit=10, offset=0)
    assert len(sessions) >= 5

    # Test pagination
    page1 = store.list_call_sessions(limit=2, offset=0)
    assert len(page1) == 2

    page2 = store.list_call_sessions(limit=2, offset=2)
    assert len(page2) == 2


def test_list_call_sessions_with_filters(store):
    """Test filtering call sessions by from_number and status."""
    # Create calls with different attributes
    store.create_turn(call_id="CA_FILTER_1", language="en", user_text="Test", intent="generic", tool_calls=None, assistant_text="R")
    store.update_call_session(call_id="CA_FILTER_1", from_number="+1111111111", status="completed")

    store.create_turn(call_id="CA_FILTER_2", language="en", user_text="Test", intent="generic", tool_calls=None, assistant_text="R")
    store.update_call_session(call_id="CA_FILTER_2", from_number="+2222222222", status="in-progress")

    # Filter by from_number
    sessions = store.list_call_sessions(from_number="+1111111111")
    assert all(s["from_number"] == "+1111111111" for s in sessions)

    # Filter by status
    sessions = store.list_call_sessions(status="completed")
    assert all(s["status"] == "completed" for s in sessions)


def test_admin_list_calls_endpoint(client, store):
    """Test GET /admin/calls endpoint."""
    # Create test calls
    for i in range(3):
        store.create_turn(
            call_id=f"CA_ADMIN_{i}",
            language="en",
            user_text="Test",
            intent="generic",
            tool_calls=None,
            assistant_text="Response",
        )

    response = client.get("/admin/calls?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "calls" in data
    assert isinstance(data["calls"], list)
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_admin_get_call_endpoint(client, store):
    """Test GET /admin/calls/{call_id} endpoint."""
    # Create call with turns
    store.create_turn(
        call_id="CA_DETAIL",
        language="en",
        user_text="Hello",
        intent="generic",
        tool_calls=None,
        assistant_text="Hi there!",
    )

    response = client.get("/admin/calls/CA_DETAIL")
    assert response.status_code == 200
    data = response.json()
    assert data["call_id"] == "CA_DETAIL"
    assert "turns" in data
    assert "transcript" in data


def test_admin_get_call_not_found(client):
    """Test GET /admin/calls/{call_id} returns 404 for non-existent call."""
    response = client.get("/admin/calls/NONEXISTENT")
    assert response.status_code == 404


def test_call_session_ended_at(store):
    """Test marking call as ended."""
    store.create_turn(
        call_id="CA_END_TEST",
        language="en",
        user_text="Test",
        intent="generic",
        tool_calls=None,
        assistant_text="Response",
    )

    # Mark as ended
    store.update_call_session(
        call_id="CA_END_TEST",
        status="completed",
        ended_at=True,
    )

    # Verify ended_at is set
    session = store.get_call_session("CA_END_TEST")
    assert session is not None
    assert session["ended_at"] is not None
    assert session["status"] == "completed"
