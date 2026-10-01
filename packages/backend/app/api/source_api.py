"""Owner-scoped document sources; durable tasks are recoverable without Pub/Sub."""

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.core.security import get_current_user
from app.models.knowledge import KnowledgeBase
from app.models.source import Source, SourceRevision, SourceSyncTask
from app.models.user import User
from app.schemas.source import SourceCreate
from app.services.file_storage import UPLOAD_ROOT, remove_uploads

router = APIRouter(tags=["资料来源"])
SOURCE_ROOT = UPLOAD_ROOT / "sources"
DOCUMENT_EXTS = {".md", ".markdown", ".txt", ".text", ".pdf", ".docx", ".doc"}


async def owned_source(session: AsyncSession, source_id: str, user_id: str, *, lock: bool = False) -> Source:
    statement = select(Source).where(Source.id == source_id, Source.user_id == user_id, Source.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "资料来源不存在")
    return row


def source_payload(source: Source) -> dict[str, Any]:
    return {"id": source.id, "knowledge_base_id": source.knowledge_base_id, "name": source.name,
            "kind": source.kind, "current_revision_id": source.current_revision_id,
            "active_task_id": source.active_task_id, "archived_at": source.archived_at}


@router.post("/sources", status_code=201)
async def create_source(body: SourceCreate, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        await session.execute(select(User).where(User.id == user.id).with_for_update(read=True, key_share=True))
        kb = (await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == str(body.knowledge_base_id),
                                    KnowledgeBase.user_id == user.id).with_for_update())).scalar_one_or_none()
        if kb is None:
            raise HTTPException(404, "知识库不存在")
        source = Source(user_id=user.id, knowledge_base_id=kb.id, name=body.name, kind=body.kind)
        session.add(source)
        await session.commit()
        return source_payload(source)


@router.get("/sources")
async def list_sources(knowledge_base_id: uuid.UUID | None = None, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        stmt = select(Source).where(Source.user_id == user.id, Source.deleted_at.is_(None))
        if knowledge_base_id:
            stmt = stmt.where(Source.knowledge_base_id == str(knowledge_base_id))
        rows = (await session.execute(stmt.order_by(Source.created_at.desc()))).scalars().all()
        return {"items": [source_payload(row) for row in rows]}


@router.post("/sources/{source_id}/revisions", status_code=202)
async def upload_revision(source_id: uuid.UUID, file: UploadFile, user: User = Depends(get_current_user)) -> dict[str, Any]:
    source_id_text = str(source_id)
    filename = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if suffix not in DOCUMENT_EXTS:
        raise HTTPException(422, "第一阶段仅支持文档来源")
    async with async_session() as session:
        await owned_source(session, source_id_text, user.id)
    revision_id = str(uuid.uuid4())
    directory = SOURCE_ROOT / source_id_text
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{revision_id}{suffix}"
    digest = hashlib.sha256()
    total = 0
    keep = False
    try:
        with path.open("wb") as output:
            while data := await file.read(1024 * 1024):
                total += len(data)
                if total > 50 * 1024 * 1024:
                    raise HTTPException(413, "文件大小超过50MB")
                digest.update(data)
                output.write(data)
        if total == 0:
            raise HTTPException(422, "文件为空")
        async with async_session() as session:
            await session.execute(select(User).where(User.id == user.id).with_for_update(read=True, key_share=True))
            source = await owned_source(session, source_id_text, user.id, lock=True)
            if source.archived_at:
                raise HTTPException(409, "来源已归档")
            if source.active_task_id:
                task = await session.get(SourceSyncTask, source.active_task_id)
                if task and task.status in {"pending", "processing"}:
                    raise HTTPException(409, "已有同步任务")
            from app.core.config import settings
            pipeline = f"located-v1:{settings.embedding_model}"
            old = (await session.execute(select(SourceRevision).where(SourceRevision.source_id == source.id,
                                        SourceRevision.raw_hash == digest.hexdigest(), SourceRevision.pipeline_version == pipeline))).scalar_one_or_none()
            if old and old.state == "ready":
                if source.current_revision_id != old.id:
                    raise HTTPException(409, "该内容是历史版本，第一阶段不支持回滚发布")
                return {"source_id": source.id, "revision_id": old.id, "status": "completed", "task_id": None}
            if old:
                revision = old
                previous_path = revision.file_path
                revision.state = "staging"
                revision.file_path = str(path)
                revision.filename = filename
            else:
                previous_path = None
                revision = SourceRevision(id=revision_id, source_id=source.id, raw_hash=digest.hexdigest(),
                                          pipeline_version=pipeline, file_path=str(path), filename=filename)
                session.add(revision)
                await session.flush()
            task = SourceSyncTask(source_id=source.id, revision_id=revision.id, user_id=user.id)
            session.add(task)
            await session.flush()
            source.active_task_id = task.id
            await session.commit()
            keep = True
        if previous_path:
            old_path = Path(previous_path)
            if old_path.resolve().is_relative_to(SOURCE_ROOT.resolve()):
                old_path.unlink(missing_ok=True)
        # Durable pending rows are picked up by worker cron even if Redis is offline.
        try:
            from app.api.import_api import get_arq
            await (await get_arq()).enqueue_job("process_source_import", task.id, _job_id=f"source:{task.id}")
        except Exception:
            pass
        return {"source_id": source_id_text, "revision_id": revision.id, "task_id": task.id, "status": task.status}
    finally:
        if not keep:
            path.unlink(missing_ok=True)


@router.get("/source-tasks/{task_id}")
async def source_task(task_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        task = (await session.execute(select(SourceSyncTask).where(SourceSyncTask.id == str(task_id), SourceSyncTask.user_id == user.id))).scalar_one_or_none()
        if task is None:
            raise HTTPException(404, "任务不存在")
        await owned_source(session, task.source_id, user.id)
        return {"id": task.id, "source_id": task.source_id, "revision_id": task.revision_id,
                "status": task.status, "stage": task.stage, "error": task.error}


@router.get("/sources/{source_id}/revisions")
async def revisions(source_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        await owned_source(session, str(source_id), user.id)
        rows = (await session.execute(select(SourceRevision).where(SourceRevision.source_id == str(source_id))
                                      .order_by(SourceRevision.created_at.desc()))).scalars().all()
        return {"items": [{"id": r.id, "raw_hash": r.raw_hash, "state": r.state, "filename": r.filename,
                           "created_at": r.created_at, "published_at": r.published_at} for r in rows]}


@router.get("/sources/{source_id}/revisions/{revision_id}/original")
async def revision_original(source_id: uuid.UUID, revision_id: uuid.UUID, user: User = Depends(get_current_user)) -> FileResponse:
    async with async_session() as session:
        await owned_source(session, str(source_id), user.id)
        revision = await session.get(SourceRevision, str(revision_id))
        if revision is None or revision.source_id != str(source_id) or not revision.file_path:
            raise HTTPException(404, "原件不可用")
        path = Path(revision.file_path).resolve()
        if not path.is_relative_to(SOURCE_ROOT.resolve()) or not path.is_file():
            raise HTTPException(404, "原件不可用")
        return FileResponse(path, filename=revision.filename or path.name, content_disposition_type="attachment")


@router.post("/sources/{source_id}/archive")
async def archive(source_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        source = await owned_source(session, str(source_id), user.id, lock=True)
        if source.active_task_id:
            task = await session.get(SourceSyncTask, source.active_task_id)
            if task and task.status in {"pending", "processing"}:
                raise HTTPException(409, "请等待同步结束再归档")
        source.archived_at = datetime.now(timezone.utc)
        await session.commit()
        return source_payload(source)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: uuid.UUID, user: User = Depends(get_current_user)) -> None:
    from app.services.source_cleanup import redact_source

    async with async_session() as session:
        await owned_source(session, str(source_id), user.id, lock=True)
        paths = await redact_source(session, str(source_id))
        await session.commit()
    remove_uploads(paths)
