"""Recoverable source import jobs and impact event maintenance."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.db import async_session as async_session
from app.models.knowledge import KnowledgeBase
from app.models.source import Source, SourceRevision, SourceSyncTask
from app.services.impact_service import process_impact_events as process_impact_events
from app.services.source_extraction import extract_documents
from app.services.source_publication import (
    document_chunks,
    publish_revision,
    store_revision_documents,
)
from app.services.vectorizer import encode_texts as encode_texts

logger = logging.getLogger(__name__)


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
    async with async_session() as image_session:
        image_task = await image_session.get(SourceSyncTask, task_id)
        image_source = await image_session.get(Source, image_task.source_id) if image_task else None
        is_image = image_source is not None and image_source.kind == "image"
    if is_image:
        from app.services.image_source_jobs import process_image_import
        return await process_image_import(ctx, task_id)
    async with async_session() as session:
        task = await session.get(SourceSyncTask, task_id)
        if task is None:
            return {"status": "cancelled"}
        source = (await session.execute(select(Source).where(Source.id == task.source_id).with_for_update())).scalar_one_or_none()
        await session.refresh(task)
        if source is None or source.deleted_at or source.archived_at or source.active_task_id != task_id or task.status != "pending":
            return {"status": "cancelled"}
        repository = source.kind in {"git_local", "git_public"}
        revision = await session.get(SourceRevision, task.revision_id) if task.revision_id else None
        if not repository and (revision is None or not revision.file_path):
            return {"status": "cancelled"}
        source_id, revision_id = source.id, revision.id if revision else None
        path, expected_head = revision.file_path if revision else None, source.current_revision_id
        kind, owner_id = source.kind, source.user_id
        config: dict[str, Any] = dict(source.config)
        task.status, task.stage = "processing", "parsing"
        await session.commit()
    try:
        ready_revision = False
        if repository:
            from app.core.config import settings
            from app.services.connectors.git_local import collect_local
            from app.services.connectors.git_public import collect_public
            from app.services.repo_access import local_repository, source_config

            config = source_config(kind, config, owner_id)
            includes: tuple[str, ...] = tuple(config.get("include_paths", []))
            if kind == "git_local":
                target, roots = local_repository(config, owner_id)
                snapshot = await asyncio.to_thread(collect_local, target, allowed_roots=roots, authorized=True,
                                                  git_executable=settings.source_git_executable, include_paths=includes)
            else:
                snapshot = await asyncio.to_thread(collect_public, config["url"],
                    cache_root=Path(settings.source_repo_cache_dir) / source_id,
                    git_executable=settings.source_git_executable, include_paths=includes)
            documents = snapshot.documents
            pipeline = f"git-v1:{snapshot.config_fingerprint}:{settings.embedding_model}"
            async with async_session() as session:
                source = (await session.execute(select(Source).where(Source.id == source_id).with_for_update())).scalar_one()
                task = await session.get(SourceSyncTask, task_id)
                if task is None or source.deleted_at or source.archived_at or source.active_task_id != task_id:
                    return {"status": "cancelled"}
                revision = (await session.execute(select(SourceRevision).where(SourceRevision.source_id == source_id,
                    SourceRevision.raw_hash == snapshot.commit, SourceRevision.pipeline_version == pipeline))).scalar_one_or_none()
                if revision is None:
                    revision = SourceRevision(source_id=source_id, raw_hash=snapshot.commit, pipeline_version=pipeline,
                        commit=snapshot.commit, manifest={**snapshot.manifest, "dirty": snapshot.dirty,
                                                        "included_count": len(snapshot.documents),
                                                        "config_fingerprint": snapshot.config_fingerprint})
                    session.add(revision)
                    await session.flush()
                ready_revision = revision.state == "ready"
                source.last_sync_manifest = {**snapshot.manifest, "dirty": snapshot.dirty,
                                             "included_count": len(snapshot.documents)}
                if not ready_revision:
                    revision.state = "staging"
                revision_id = revision.id
                task.revision_id = revision_id
                task.stage = "indexing"
                await session.commit()
        else:
            if path is None:
                raise ValueError("原件不可用")
            documents = await asyncio.to_thread(lambda: asyncio.run(extract_documents(Path(path))))
        chunks = document_chunks(documents)
        if revision_id is None:
            raise ValueError("同步版本不可用")
        if not chunks or len(chunks) > 10000:
            raise ValueError("文档为空或片段超过上限")
        async with async_session() as session:
            task = await session.get(SourceSyncTask, task_id)
            if task:
                task.stage = "indexing"
                await session.commit()
        vectors = [] if ready_revision else (await encode_texts([chunk.text for chunk in chunks])).tolist()
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
            if repository:
                source_config(source.kind, source.config, source.user_id)
            if not ready_revision:
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
        pending = list((await session.execute(select(SourceSyncTask.id)
            .where(SourceSyncTask.status == "pending")
            .order_by(SourceSyncTask.created_at, SourceSyncTask.id).limit(100))).scalars())
        stale = list((await session.execute(select(SourceSyncTask.id)
            .where(SourceSyncTask.status == "processing",
                   SourceSyncTask.updated_at < datetime.now(timezone.utc) - timedelta(minutes=15))
            .order_by(SourceSyncTask.updated_at, SourceSyncTask.id).limit(100))).scalars())
    for task_id in stale:
        await mark_failed(task_id)
    for task_id in pending:
        try:
            await ctx["redis"].enqueue_job("process_source_import", task_id, _job_id=f"source:{task_id}")
        except Exception:
            # The durable pending row is retried next tick; unrelated recovery must continue.
            logger.warning("Source task enqueue failed; will retry: %s", task_id)
    await process_impact_events()
    async with async_session() as session:
        await retry_source_cleanup(session)
