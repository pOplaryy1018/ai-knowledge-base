"""Authorized uploads with durable, reconnectable progress."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.db import async_session
from app.core.security import get_current_user
from app.models.import_task import ImportTask
from app.models.knowledge import KnowledgeBase, KnowledgeFile
from app.models.user import User
from app.schemas.import_schema import ImportTaskResponse
from app.services.file_storage import UPLOAD_ROOT
from app.services.file_types import SUPPORTED_EXTS
from app.services.import_tasks import enqueue_import, load_task, task_event

router = APIRouter(prefix="/import", tags=["文档导入"])
UPLOAD_DIR = UPLOAD_ROOT
_arq_pool: ArqRedis | None = None


async def get_arq() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


@router.post("/upload", response_model=ImportTaskResponse, status_code=202)
async def upload_file(file: UploadFile, kb_id: str = Query(...), current_user: User = Depends(get_current_user)) -> ImportTaskResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    filename = Path(file.filename.replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {suffix}")
    async with async_session() as session:
        kb = await session.get(KnowledgeBase, kb_id)
        if kb is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        if current_user.role != "super_admin" and kb.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权操作该知识库")

    file_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = UPLOAD_DIR / f"{file_id}{suffix}"
    total_size = 0
    try:
        with save_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > 50 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="文件大小超过 50MB 限制")
                output.write(chunk)
        async with async_session() as session:
            owner = await session.execute(select(User).where(User.id == current_user.id).with_for_update())
            if owner.scalar_one_or_none() is None:
                raise HTTPException(status_code=401, detail="用户已被删除")
            result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id).with_for_update())
            if result.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="知识库不存在")
            kf = KnowledgeFile(id=file_id, knowledge_base_id=kb_id, user_id=current_user.id, filename=save_path.name, original_filename=filename, file_path=str(save_path), file_type=suffix.lstrip("."), file_size=total_size, status="pending", active_task_id=task_id)
            task = ImportTask(id=task_id, file_id=file_id, user_id=current_user.id)
            session.add(kf)
            await session.flush()
            session.add(task)
            await session.commit()
    except BaseException:
        save_path.unlink(missing_ok=True)
        raise
    await enqueue_import(task, kf, get_arq)
    return ImportTaskResponse(file_id=file_id, task_id=task_id, filename=filename, status="pending")


@router.get("/{task_id}/status")
async def get_import_status(task_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    return task_event(await load_task(task_id, user))


@router.get("/{task_id}/progress")
async def get_import_progress(task_id: str, user: User = Depends(get_current_user)) -> EventSourceResponse:
    await load_task(task_id, user)

    async def event_generator() -> Any:
        # Replayable snapshots avoid Pub/Sub's lost-event and subscription gaps.
        last_payload = ""
        while True:
            try:
                event = task_event(await load_task(task_id, user))
            except HTTPException:
                event = {"type": "error", "error": "任务已删除或不再可访问"}
            payload = json.dumps(event, ensure_ascii=False)
            if payload != last_payload:
                yield {"event": event["type"], "data": payload}
                last_payload = payload
            if event["type"] in {"complete", "error"}:
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
