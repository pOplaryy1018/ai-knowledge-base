import pytest


@pytest.mark.asyncio
async def test_login_endpoint_exists(client):
    """验证登录端点可访问（空请求体应返回 422 校验错误）"""
    response = await client.post("/api/auth/login", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_endpoint_exists(client):
    """验证注册端点可访问（空请求体应返回 422 校验错误）"""
    response = await client.post("/api/auth/register", json={})
    assert response.status_code == 422
