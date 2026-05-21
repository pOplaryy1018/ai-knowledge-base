"""Redis 连接管理"""

from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis | None = None


async def get_redis() -> Redis:
    """获取 Redis 客户端实例"""
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return redis_client


async def check_redis_health() -> str:
    """检查 Redis 连接是否正常"""
    try:
        r = await get_redis()
        await r.ping()
        _ = None
        return "connected"
    except Exception:
        return "disconnected"


async def init_redis() -> None:
    """初始化 Redis 连接"""
    global redis_client
    redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
