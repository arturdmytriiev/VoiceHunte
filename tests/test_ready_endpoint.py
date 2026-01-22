"""
Comprehensive tests for /ready endpoint with dependency health checks.

Tests verify that the /ready endpoint correctly:
- Returns 200 when all dependencies are healthy
- Returns 503 when any dependency fails
- Reports which specific dependency failed
- Respects timeouts on slow dependencies
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psycopg
import pytest
import requests
from fastapi.testclient import TestClient

from app import main
from app.core.config import settings


def test_ready_all_dependencies_healthy(postgres_dsn: str) -> None:
    """Test /ready returns 200 when all dependencies are healthy."""
    client = TestClient(main.app)

    # Mock Qdrant and OpenAI responses
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with (
        patch("requests.get", return_value=mock_response),
        patch.object(settings, "openai_api_key", "test_key"),
    ):
        response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["checks"]["postgres"]["status"] == "ok"
    assert data["checks"]["qdrant"]["status"] == "ok"
    assert data["checks"]["openai"]["status"] == "ok"


def test_ready_postgres_failure(postgres_dsn: str) -> None:
    """Test /ready returns 503 when Postgres is unavailable."""
    client = TestClient(main.app)

    # Mock successful Qdrant and OpenAI responses
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    # Temporarily break Postgres by using invalid DSN
    invalid_dsn = "postgresql://invalid:invalid@localhost:9999/invalid"

    with (
        patch("requests.get", return_value=mock_response),
        patch.object(settings, "openai_api_key", "test_key"),
        patch.object(settings, "postgres_dsn", invalid_dsn),
        patch("app.main.get_pool") as mock_get_pool,
    ):
        # Mock pool to raise connection error
        mock_pool = MagicMock()
        mock_pool.connection.side_effect = psycopg.OperationalError("Connection refused")
        mock_get_pool.return_value = mock_pool

        response = client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert data["checks"]["postgres"]["status"] == "error"
    assert "Connection refused" in data["checks"]["postgres"]["error"]


def test_ready_qdrant_failure() -> None:
    """Test /ready returns 503 when Qdrant is unavailable."""
    client = TestClient(main.app)

    def mock_get(url, **kwargs):
        if "qdrant" in url or "collections" in url:
            raise requests.ConnectionError("Connection refused")
        # Mock successful OpenAI response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        return mock_response

    with (
        patch("requests.get", side_effect=mock_get),
        patch.object(settings, "openai_api_key", "test_key"),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert data["checks"]["qdrant"]["status"] == "error"
    assert "Connection refused" in data["checks"]["qdrant"]["error"]


def test_ready_openai_api_key_missing() -> None:
    """Test /ready returns 503 when OpenAI API key is not configured."""
    client = TestClient(main.app)

    # Mock successful Qdrant response
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with (
        patch("requests.get", return_value=mock_response),
        patch.object(settings, "openai_api_key", None),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert data["checks"]["openai"]["status"] == "error"
    assert "openai_api_key missing" in data["checks"]["openai"]["error"]


def test_ready_openai_api_failure() -> None:
    """Test /ready returns 503 when OpenAI API is unreachable."""
    client = TestClient(main.app)

    def mock_get(url, **kwargs):
        if "openai" in url or "api.openai.com" in url:
            raise requests.Timeout("Request timed out")
        # Mock successful Qdrant response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        return mock_response

    with (
        patch("requests.get", side_effect=mock_get),
        patch.object(settings, "openai_api_key", "test_key"),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert data["checks"]["openai"]["status"] == "error"
    assert "timed out" in data["checks"]["openai"]["error"].lower()


def test_ready_multiple_failures() -> None:
    """Test /ready reports multiple failures when multiple dependencies are down."""
    client = TestClient(main.app)

    def mock_get(url, **kwargs):
        # Both Qdrant and OpenAI fail
        raise requests.ConnectionError("Network error")

    with (
        patch("requests.get", side_effect=mock_get),
        patch.object(settings, "openai_api_key", "test_key"),
        patch("app.main.get_pool") as mock_get_pool,
    ):
        # Postgres also fails
        mock_pool = MagicMock()
        mock_pool.connection.side_effect = psycopg.OperationalError("DB down")
        mock_get_pool.return_value = mock_pool

        response = client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"

    # All three should be marked as failed
    assert data["checks"]["postgres"]["status"] == "error"
    assert data["checks"]["qdrant"]["status"] == "error"
    assert data["checks"]["openai"]["status"] == "error"


def test_ready_timeout_handling(postgres_dsn: str) -> None:
    """
    Test that /ready respects timeouts and doesn't hang on slow dependencies.

    The /ready endpoint should timeout checks after 1.5 seconds to prevent
    the health check itself from becoming a bottleneck.
    """
    client = TestClient(main.app)

    def slow_get(url, **kwargs):
        """Simulate a very slow response that would exceed timeout."""
        import time

        time.sleep(3)  # Exceeds 1.5s timeout
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        return mock_response

    with (
        patch("requests.get", side_effect=slow_get),
        patch.object(settings, "openai_api_key", "test_key"),
    ):
        # This should complete quickly and mark dependencies as failed due to timeout
        response = client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    # At least one of Qdrant or OpenAI should have timed out
    assert (
        data["checks"]["qdrant"]["status"] == "error"
        or data["checks"]["openai"]["status"] == "error"
    )


def test_ready_json_structure() -> None:
    """Test that /ready returns proper JSON structure regardless of status."""
    client = TestClient(main.app)

    # Mock all dependencies to fail
    with (
        patch("requests.get", side_effect=requests.ConnectionError("Failed")),
        patch.object(settings, "openai_api_key", "test_key"),
        patch("app.main.get_pool") as mock_get_pool,
    ):
        mock_pool = MagicMock()
        mock_pool.connection.side_effect = psycopg.OperationalError("Failed")
        mock_get_pool.return_value = mock_pool

        response = client.get("/ready")

    data = response.json()

    # Verify structure
    assert "status" in data
    assert "checks" in data
    assert isinstance(data["checks"], dict)

    # Each check should have status and error (if failed)
    for service in ["postgres", "qdrant", "openai"]:
        assert service in data["checks"]
        assert "status" in data["checks"][service]
        if data["checks"][service]["status"] == "error":
            assert "error" in data["checks"][service]
