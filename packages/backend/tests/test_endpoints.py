from unittest.mock import AsyncMock


def test_admin_create_password_is_body_not_url():
    from app.main import app

    endpoint = app.openapi()["paths"]["/api/auth/users"]["post"]
    assert "requestBody" in endpoint
    assert not any(param["name"] == "password" for param in endpoint.get("parameters", []))


async def test_readiness_fails_when_dependency_is_down(client, monkeypatch):
    from app.api import health

    monkeypatch.setattr(health, "check_database_health", AsyncMock(return_value="disconnected"))
    monkeypatch.setattr(health, "check_redis_health", AsyncMock(return_value="connected"))
    response = await client.get("/api/ready")
    assert response.status_code == 503
