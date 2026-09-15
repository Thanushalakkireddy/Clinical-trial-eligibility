import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client: TestClient):
    """Test that GET /health returns status: ok and the service name."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "clinical-trial-eligibility-api"


def test_health_reports_configuration_as_booleans_only(client: TestClient):
    """Configuration status is reported as booleans; never secrets or values."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert "gemini_configured" in data
    assert "database_configured" in data
    assert isinstance(data["gemini_configured"], bool)
    assert isinstance(data["database_configured"], bool)

    # The body must not expose credential material or configuration values.
    body = response.text.lower()
    for secret_marker in ("api-key", "api_key", "password", "postgresql", "postgres"):
        assert secret_marker not in body
