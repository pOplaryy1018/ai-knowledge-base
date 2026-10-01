"""Import task ownership, snapshots and recoverable scheduling."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.db import async_session
from app.models.import_task import ImportTask
from app.models.knowledge import KnowledgeBase, KnowledgeFile, KnowledgeItem
from app.models.user import User


def verify_task_access(task: ImportTask, user: User) -> None:
    if user.role != "super_admin" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问此导入任务")


def task_event(task: ImportTask) -> dict[str, Any]:
    if task.status == "completed":
        return {"type": "complete", "total_chunks": task.chunks_count, "percent": 100}
    if task.status in {"failed", "cancelled"}:
        return {"type": "error", "error": task.error_message or "任务已取消"}
    return {"type": "progress", "stage": task.stage, "message": task.message, "percent": task.percent}


async def load_task(task_id: str, user: User) -> ImportTask:
    async with async_session() as session:
        task = await session.get(ImportTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="导入任务不存在")
        verify_task_access(task, user)
        # Hard-killed workers cannot write terminal state; allow explicit retry after deadline.
        updated = task.updated_at.replace(tzinfo=timezone.utc) if task.updated_at.tzinfo is None else task.updated_at
        stale = (datetime.now(timezone.utc) - updated).total_seconds() > 900
        lost = task.status == "pending" and stale and not await queue_job_exists(task.id)
        if stale and (task.status == "processing" or lost):
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.id == task.file_id).with_for_update())
            file = result.scalar_one_or_none()
            if file is None:
                raise HTTPException(status_code=404, detail="导入任务不存在")
            await session.refresh(task)
            if file.active_task_id == task.id and (task.status == "processing" or (lost and task.status == "pending")):
                task.status = file.status = "failed"
                task.error_message = file.error_message = "任务丢失或处理超时，请重试"
                await session.commit()
        return task


async def queue_job_exists(task_id: str) -> bool:
    """Only confirmed queue loss invalidates pending work; preserve legitimate backlogs."""
    from arq.jobs import Job, JobStatus

    from app.api.import_api import get_arq

    try:
        async with asyncio.timeout(3):
            return await Job(task_id, await get_arq()).status() != JobStatus.not_found
    except Exception:
        # Redis unavailability is not proof that a queued job has disappeared.
        return True


async def enqueue_import(task: ImportTask, file: KnowledgeFile, get_queue: Callable[[], Awaitable[Any]]) -> None:
    try:
        queue = await get_queue()
        job = await queue.enqueue_job("process_import", _job_id=task.id, task_id=task.id, file_id=file.id, kb_id=file.knowledge_base_id, file_path=file.file_path, filename=file.original_filename)
        if job is None:
            raise RuntimeError("task was not scheduled")
    except Exception as error:
        # An accepted job may already be running even if the Redis response was lost.
        # Only a still-pending attempt can become retryable; preserve all later states.
        await update_task(task.id, status="failed", stage="failed", message="任务入队失败，请重试", error="任务入队失败，请重试", claim=True)
        raise HTTPException(status_code=503, detail="任务入队失败，文件已保留，可重试") from error


async def update_task(task_id: str, *, status: str = "processing", stage: str = "processing", message: str = "处理中", percent: int = 0, error: str | None = None, claim: bool = False) -> bool:
    async with async_session() as session:
        task = await session.get(ImportTask, task_id)
        if not task:
            return False
        result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.id == task.file_id).with_for_update())
        file = result.scalar_one_or_none()
        if not file:
            return False
        await session.refresh(task)
        if not file or file.active_task_id != task_id or task.status in {"completed", "failed", "cancelled"}:
            return False
        if claim and task.status != "pending":
            return False
        task.status = file.status = status
        task.stage, task.message, task.percent = stage, message, percent
        task.error_message = file.error_message = error
        await session.commit()
        return True


async def finish_import(task_id: str, chunks: Any, vectors: Any, metadata: dict[str, object]) -> int | None:
    from app.services.vectorizer import store_chunks

    async with async_session() as session:
        task = await session.get(ImportTask, task_id)
        if not task:
            return None
        kb_id = (await session.execute(select(KnowledgeFile.knowledge_base_id).where(KnowledgeFile.id == task.file_id))).scalar_one_or_none()
        if not kb_id:
            return None
        parent = await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id).with_for_update())
        if parent.scalar_one_or_none() is None:
            return None
        result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.id == task.file_id).with_for_update())
        file = result.scalar_one_or_none()
        if not file:
            return None
        await session.refresh(task)
        if not file or file.active_task_id != task_id or task.status != "processing":
            return None
        await session.execute(delete(KnowledgeItem).where(KnowledgeItem.file_id == file.id))
        count = await store_chunks(file.knowledge_base_id, chunks, vectors, file_id=file.id, source_metadata_base=metadata, session=session)
        task.status = file.status = "completed"
        task.chunks_count = file.chunks_count = count
        task.percent, task.stage, task.message = 100, "completed", "导入完成"
        task.error_message = file.error_message = None
        await session.commit()
        return count
