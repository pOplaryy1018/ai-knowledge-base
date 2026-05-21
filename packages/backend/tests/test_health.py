import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """验证健康检查端点返回 200"""
    response = await client.get("/api/health")
    assert response.status_code == 200
