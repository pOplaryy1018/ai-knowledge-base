"""FastAPI 应用入口 ── AI 知识库管理平台后端"""

from collections.abc import AsyncIterator
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import engine
from app.core.redis import init_redis, close_redis
from app.api.health import router as health_router
from app.routers.auth import router as auth_router
from app.routers.knowledge import router as knowledge_router
from app.api.import_api import router as import_router
from app.routers.agent import router as agent_router
from app.routers.chat import router as chat_router
from app.routers.file import router as file_router
from app.routers.statistics import router as statistics_router
from app.seed import seed_admin


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动时初始化资源，关闭时释放资源"""
    # 启动时初始化 Redis 并确保管理员存在
    await init_redis()
    await seed_admin()
    yield
    # 关闭时释放资源
    await close_redis()
    await engine.dispose()


app: FastAPI = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(import_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(file_router, prefix="/api")
app.include_router(statistics_router, prefix="/api")


@app.get("/")
async def root() -> dict[str, Any]:
    """根路径重定向提示"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
