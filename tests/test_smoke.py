import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_healthz_returns_200(self, client: TestClient):
        """Test that /healthz returns 200 OK."""
        response = client.get("/healthz")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "environment" in data
        assert "version" in data

    def test_root_returns_info(self, client: TestClient):
        """Test that root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "docs" in data


class TestSwaggerDocs:
    """Tests for API documentation endpoints."""

    def test_swagger_ui_available(self, client: TestClient):
        """Test that Swagger UI is available at /docs."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_json_available(self, client: TestClient):
        """Test that OpenAPI JSON schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert "openapi" in data
        assert "paths" in data
        assert "/healthz" in data["paths"]

    def test_redoc_available(self, client: TestClient):
        """Test that ReDoc is available at /redoc."""
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
