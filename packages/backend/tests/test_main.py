import pytest


@pytest.mark.asyncio
async def test_root_path(client):
    """验证根路径返回服务名称与版本"""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "version" in data
    assert data["service"] == "AI 知识库管理平台"
