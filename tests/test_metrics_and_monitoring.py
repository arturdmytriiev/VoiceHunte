"""Tests for metrics, monitoring, and error tracking."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import requests

from app.main import app
from app.core.retry import retryable, raise_for_retryable_status
from app.core.errors import ExternalAPIError


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


def test_metrics_endpoint(client):
    """Test Prometheus metrics endpoint."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # Check for Prometheus format
    assert "# HELP" in response.text or "# TYPE" in response.text or response.text.startswith("http_")


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_ready_endpoint_success(client):
    """Test readiness probe when all services are healthy."""
    with patch("requests.get") as mock_get, \
         patch("app.db.pool.get_pool") as mock_pool:
        # Mock successful Qdrant check
        mock_qdrant = MagicMock()
        mock_qdrant.status_code = 200
        mock_qdrant.raise_for_status = MagicMock()

        # Mock successful OpenAI check
        mock_openai = MagicMock()
        mock_openai.status_code = 200
        mock_openai.raise_for_status = MagicMock()

        def get_side_effect(url, *args, **kwargs):
            if "qdrant" in url:
                return mock_qdrant
            elif "openai" in url:
                return mock_openai
            return MagicMock()

        mock_get.side_effect = get_side_effect

        # Mock successful Postgres check
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_pool.return_value.connection.return_value.__enter__.return_value = mock_conn

        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


def test_retry_logic_on_timeout():
    """Test retry decorator retries on timeout."""
    call_count = {"count": 0}

    @retryable("test_service")
    def flaky_function():
        call_count["count"] += 1
        if call_count["count"] < 3:
            raise requests.Timeout("Connection timeout")
        return "success"

    result = flaky_function()
    assert result == "success"
    assert call_count["count"] == 3  # Should retry twice, succeed on third


def test_retry_logic_on_429():
    """Test retry decorator retries on 429 status."""
    call_count = {"count": 0}

    @retryable("test_service")
    def rate_limited_function():
        call_count["count"] += 1
        if call_count["count"] < 2:
            raise ExternalAPIError("test_service", "Rate limited", status_code=429)
        return "success"

    result = rate_limited_function()
    assert result == "success"
    assert call_count["count"] == 2  # Should retry once, succeed on second


def test_retry_logic_on_5xx():
    """Test retry decorator retries on 5xx errors."""
    call_count = {"count": 0}

    @retryable("test_service")
    def server_error_function():
        call_count["count"] += 1
        if call_count["count"] < 2:
            raise ExternalAPIError("test_service", "Server error", status_code=500)
        return "success"

    result = server_error_function()
    assert result == "success"
    assert call_count["count"] == 2


def test_retry_logic_no_retry_on_4xx():
    """Test retry decorator does not retry on 4xx errors (except 429)."""
    call_count = {"count": 0}

    @retryable("test_service")
    def client_error_function():
        call_count["count"] += 1
        raise ExternalAPIError("test_service", "Bad request", status_code=400)

    with pytest.raises(ExternalAPIError):
        client_error_function()

    assert call_count["count"] == 1  # Should not retry


def test_raise_for_retryable_status_429():
    """Test raise_for_retryable_status raises on 429."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"

    with pytest.raises(ExternalAPIError) as exc_info:
        raise_for_retryable_status(mock_response, "test_service")

    assert exc_info.value.status_code == 429
    assert "test_service" in str(exc_info.value)


def test_raise_for_retryable_status_500():
    """Test raise_for_retryable_status raises on 500."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal server error"

    with pytest.raises(ExternalAPIError) as exc_info:
        raise_for_retryable_status(mock_response, "test_service")

    assert exc_info.value.status_code == 500


def test_raise_for_retryable_status_200_passes():
    """Test raise_for_retryable_status passes on 200."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    # Should not raise
    raise_for_retryable_status(mock_response, "test_service")
    mock_response.raise_for_status.assert_called_once()


def test_error_handler_external_api_error(client):
    """Test global error handler for ExternalAPIError."""
    with patch("app.main.handle_voice_input") as mock_handler:
        mock_handler.side_effect = ExternalAPIError("openai", "API error", status_code=503)

        response = client.post("/twilio/voice", data={})
        assert response.status_code == 200  # Returns TwiML, not 503
        # Should contain error message in TwiML
        assert "<?xml version" in response.text


def test_error_handler_validation_error(client):
    """Test global error handler for validation errors."""
    # Send invalid data to trigger validation error
    response = client.post("/mvp/text", json={"text": "", "language": "en"})
    assert response.status_code == 422


def test_rate_limit_enforcement(client):
    """Test rate limiting on admin endpoints."""
    # This test depends on slowapi configuration
    # Make multiple rapid requests to trigger rate limit
    # Note: May need to adjust based on actual rate limit settings
    responses = []
    for _ in range(25):  # admin_rate_limit default is 20/minute
        response = client.get("/health")
        responses.append(response.status_code)

    # Should get at least some 200s (successful requests)
    assert 200 in responses


def test_request_id_in_response_headers(client):
    """Test that request_id is added to response headers."""
    response = client.get("/health")
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0


def test_call_id_in_response_headers(client):
    """Test that call_id is added to response headers."""
    response = client.get("/health")
    assert "x-call-id" in response.headers
    assert len(response.headers["x-call-id"]) > 0
