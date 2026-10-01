"""Recoverable source import jobs and impact event maintenance."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.db import async_session
from app.models.knowledge import KnowledgeBase
from app.models.source import Source, SourceRevision, SourceSyncTask
from app.services.impact_service import process_impact_events
from app.services.source_extraction import extract_documents
from app.services.source_publication import (
    document_chunks,
    publish_revision,
    store_revision_documents,
)
from app.services.vectorizer import encode_texts


async def mark_failed(task_id: str) -> None:
    async with async_session() as session:
        task = await session.get(SourceSyncTask, task_id)
        if task is None:
            return
        source = (await session.execute(select(Source).where(Source.id == task.source_id).with_for_update())).scalar_one_or_none()
        await session.refresh(task)
        if source is None or source.active_task_id != task_id or task.status == "completed":
            return
        task.status, task.stage, task.error = "failed", "failed", "解析或索引失败，请检查文件与服务后重新上传"
        source.active_task_id = None
        revision = await session.get(SourceRevision, task.revision_id) if task.revision_id else None
        if revision and revision.published_at is None:
            revision.state = "failed"
        await session.commit()


async def process_source_import(ctx: Any, task_id: str) -> dict[str, str]:
    async with async_session() as session:
        task = await session.get(SourceSyncTask, task_id)
        if task is None:
            return {"status": "cancelled"}
        source = (await session.execute(select(Source).where(Source.id == task.source_id).with_for_update())).scalar_one_or_none()
        await session.refresh(task)
        if source is None or source.deleted_at or source.archived_at or source.active_task_id != task_id or task.status != "pending":
            return {"status": "cancelled"}
        revision = await session.get(SourceRevision, task.revision_id)
        if revision is None or not revision.file_path:
            return {"status": "cancelled"}
        source_id, revision_id, path, expected_head = source.id, revision.id, revision.file_path, source.current_revision_id
        task.status, task.stage = "processing", "parsing"
        await session.commit()
    try:
        documents = await asyncio.to_thread(lambda: asyncio.run(extract_documents(Path(path))))
        chunks = document_chunks(documents)
        if not chunks or len(chunks) > 10000:
            raise ValueError("文档为空或片段超过上限")
        async with async_session() as session:
            task = await session.get(SourceSyncTask, task_id)
            if task:
                task.stage = "indexing"
                await session.commit()
        vectors = (await encode_texts([chunk.text for chunk in chunks])).tolist()
        async with async_session() as session:
            baseline = await session.get(Source, source_id)
            if baseline is None or baseline.knowledge_base_id is None:
                return {"status": "cancelled"}
            await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == baseline.knowledge_base_id).with_for_update(read=True, key_share=True))
            source = (await session.execute(select(Source).where(Source.id == source_id).with_for_update())).scalar_one()
            task = await session.get(SourceSyncTask, task_id)
            revision = await session.get(SourceRevision, revision_id)
            if task is None or revision is None or source.active_task_id != task_id or task.status != "processing" or source.deleted_at:
                return {"status": "cancelled"}
            await store_revision_documents(session, source, revision, documents, vectors)
            await publish_revision(session, source_id, revision_id, expected_head)
            task.status, task.stage = "completed", "published"
            source.active_task_id = None
            await session.commit()
    except asyncio.CancelledError:
        await asyncio.shield(mark_failed(task_id))
        raise
    except Exception:
        await mark_failed(task_id)
        return {"status": "failed"}
    await process_impact_events()
    return {"status": "completed"}


async def source_maintenance(ctx: Any) -> None:
    from app.services.source_cleanup import retry_source_cleanup

    async with async_session() as session:
        rows = (await session.execute(select(SourceSyncTask).where(SourceSyncTask.status.in_(["pending", "processing"])).limit(100))).scalars().all()
        pending = [row.id for row in rows if row.status == "pending"]
        stale = [row.id for row in rows if row.status == "processing" and row.updated_at < datetime.now(timezone.utc) - timedelta(minutes=15)]
    for task_id in pending:
        await ctx["redis"].enqueue_job("process_source_import", task_id, _job_id=f"source:{task_id}")
    for task_id in stale:
        await mark_failed(task_id)
    await process_impact_events()
    async with async_session() as session:
        await retry_source_cleanup(session)
