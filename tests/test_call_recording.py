"""Tests for call recording functionality."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

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


def test_save_and_get_recording(store):
    """Test saving and retrieving recording metadata."""
    # Create a call first
    store.create_turn(
        call_id="CA123",
        language="en",
        user_text="Hello",
        intent="generic",
        tool_calls=None,
        assistant_text="Hi there!",
    )

    # Save recording
    store.save_recording(
        call_id="CA123",
        recording_sid="RE123",
        recording_url="https://api.twilio.com/recordings/RE123",
        from_number="+1234567890",
        to_number="+0987654321",
    )

    # Retrieve recording
    recording = store.get_recording("CA123")
    assert recording is not None
    assert recording["call_id"] == "CA123"
    assert recording["recording_sid"] == "RE123"
    assert recording["recording_url"] == "https://api.twilio.com/recordings/RE123"
    assert recording["from_number"] == "+1234567890"
    assert recording["to_number"] == "+0987654321"


def test_get_nonexistent_recording(store):
    """Test retrieving non-existent recording returns None."""
    recording = store.get_recording("NONEXISTENT")
    assert recording is None


def test_recording_admin_endpoint(client, store):
    """Test admin endpoint for retrieving recordings."""
    # Create call and recording
    store.create_turn(
        call_id="CA456",
        language="en",
        user_text="Test",
        intent="generic",
        tool_calls=None,
        assistant_text="Response",
    )
    store.save_recording(
        call_id="CA456",
        recording_sid="RE456",
        recording_url="https://api.twilio.com/recordings/RE456",
    )

    # Test GET /admin/recordings/{call_id}
    response = client.get("/admin/recordings/CA456")
    assert response.status_code == 200
    data = response.json()
    assert data["call_id"] == "CA456"
    assert data["recording_sid"] == "RE456"


def test_recording_admin_endpoint_not_found(client):
    """Test admin endpoint returns 404 for non-existent recording."""
    response = client.get("/admin/recordings/NONEXISTENT")
    assert response.status_code == 404


def test_recording_status_webhook(client):
    """Test recording status webhook handler."""
    with patch("app.twilio.security.verify_twilio_signature") as mock_verify:
        mock_verify.return_value = True

        # Test recording completed webhook
        response = client.post(
            "/twilio/recording-status",
            data={
                "CallSid": "CA789",
                "RecordingSid": "RE789",
                "RecordingUrl": "https://api.twilio.com/recordings/RE789",
                "RecordingStatus": "completed",
                "From": "+1234567890",
                "To": "+0987654321",
            },
        )
        assert response.status_code == 200
        assert "<?xml version" in response.text


def test_recording_status_webhook_invalid_signature(client):
    """Test recording status webhook rejects invalid signature."""
    with patch("app.twilio.security.verify_twilio_signature") as mock_verify:
        mock_verify.return_value = False

        response = client.post(
            "/twilio/recording-status",
            data={
                "CallSid": "CA789",
                "RecordingSid": "RE789",
                "RecordingUrl": "https://api.twilio.com/recordings/RE789",
                "RecordingStatus": "completed",
            },
        )
        assert response.status_code == 403
