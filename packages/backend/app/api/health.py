"""健康检查接口"""

from typing import Any

from fastapi import APIRouter

from app.core.db import check_database_health
from app.core.redis import check_redis_health

router: APIRouter = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """返回服务运行状态和数据库/Redis 连接状态"""
    db_status: str = await check_database_health()
    redis_status: str = await check_redis_health()
    all_ok: bool = db_status == "connected" and redis_status == "connected"
    return {
        "status": "ok" if all_ok else "degraded",
        "database": db_status,
        "redis": redis_status,
    }
