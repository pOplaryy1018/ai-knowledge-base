"""数据库连接管理 ── SQLAlchemy 异步引擎与会话"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话（依赖注入用）"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_database_health() -> str:
    """检查数据库连接是否正常"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        return "disconnected"
