"""文档导入 API ── 上传文件 + SSE 进度推送"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.db import async_session
from app.core.security import decode_token
from app.models.user import User
from app.core.security import get_current_user
from app.models.knowledge import KnowledgeBase
from app.schemas.import_schema import ImportTaskResponse

router: APIRouter = APIRouter(prefix="/import", tags=["文档导入"])

UPLOAD_DIR: Path = Path(__file__).resolve().parents[3] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

_arq_pool: ArqRedis | None = None


async def get_arq() -> ArqRedis:
    """获取 ARQ Redis 连接池（懒加载单例）"""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def auth_sse(token: str = Query(..., description="JWT access_token")) -> User:
    """EventSource 专用认证：从查询参数读取 token"""
    payload: dict[str, Any] = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌类型错误")
    user_id: Any = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


@router.post("/upload", response_model=ImportTaskResponse, status_code=202)
async def upload_file(
    file: UploadFile,
    kb_id: str = Query(..., description="目标知识库 ID"),
    current_user: User = Depends(get_current_user),
) -> ImportTaskResponse:
    """上传文档文件 → 立即入库 → 返回 202 → 异步解析/切分/向量化"""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件名不能为空")

    suffix: str = Path(file.filename).suffix.lower()
    allowed: set[str] = {
        ".pdf", ".docx", ".doc", ".md", ".markdown", ".txt", ".text",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
        ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".json", ".yaml", ".yml", ".xml", ".toml",
    }
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {suffix}，支持: {', '.join(sorted(allowed))}",
        )

    file_id: str = str(uuid.uuid4())
    save_path: Path = UPLOAD_DIR / f"{file_id}_{file.filename}"

    # 流式写入磁盘 + 大小校验（不积压内存，边读边写）
    MAX_SIZE = 50 * 1024 * 1024
    total_size = 0
    chunk_size = 1024 * 1024  # 1MB per read
    try:
        with open(save_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="文件大小超过 50MB 限制",
                    )
                f.write(chunk)
    except HTTPException:
        # 清理已写入的部分文件
        if save_path.exists():
            save_path.unlink()
        raise

    # 校验知识库归属 + 创建文件记录（合并为一个 DB 会话）
    async with async_session() as session:
        from app.models.knowledge import KnowledgeFile

        kb_result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if not kb:
            if save_path.exists():
                save_path.unlink()
            raise HTTPException(status_code=404, detail="知识库不存在")
        if current_user.role != "super_admin" and kb.user_id != current_user.id:
            if save_path.exists():
                save_path.unlink()
            raise HTTPException(status_code=403, detail="无权操作该知识库")

        kf = KnowledgeFile(
            id=file_id,
            knowledge_base_id=kb_id,
            user_id=current_user.id,
            filename=f"{file_id}_{file.filename}",
            original_filename=file.filename,
            file_path=str(save_path),
            file_type=suffix.lstrip("."),
            file_size=total_size,
            status="pending",
        )
        session.add(kf)
        await session.commit()

    # 入队异步任务（解析 → 切分 → 向量化 → 写入 knowledge_items）
    task_id: str = str(uuid.uuid4())
    arq: ArqRedis = await get_arq()
    await arq.enqueue_job(
        "process_import",
        task_id=task_id,
        file_id=file_id,
        kb_id=kb_id,
        file_path=str(save_path),
        filename=file.filename,
    )

    return ImportTaskResponse(
        file_id=file_id,
        task_id=task_id,
        filename=file.filename,
        status="pending",
    )


@router.get("/{task_id}/progress")
async def get_import_progress(
    task_id: str,
    _user: User = Depends(auth_sse),
) -> EventSourceResponse:
    """SSE 端点：订阅导入任务进度"""

    async def event_generator() -> Any:
        redis: ArqRedis = await get_arq()
        channel_name: str = f"import_progress:{task_id}"

        yield {"event": "connected", "data": json.dumps({"status": "subscribed"})}

        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(channel_name)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    raw: Any = message["data"]
                    data_str: str = raw.decode() if isinstance(raw, bytes) else str(raw)
                    event_data: dict[str, Any] = json.loads(data_str)
                    event_type: str = str(event_data.get("type", "progress"))
                    yield {"event": event_type, "data": data_str}
                    if event_type in ("complete", "error"):
                        await pubsub.unsubscribe(channel_name)
                        break

        yield {"event": "closed", "data": json.dumps({"status": "closed"})}

    return EventSourceResponse(event_generator())
