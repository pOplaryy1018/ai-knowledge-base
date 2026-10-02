"""Image import pipeline with frozen inputs and guarded publication."""

import asyncio
from pathlib import Path
from typing import Any, cast

from sqlalchemy import delete, select

from app.core.config import settings
from app.models.knowledge import KnowledgeBase, KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision, SourceSyncTask
from app.models.user import User
from app.services.connectors import image
from app.services.source_publication import (
    document_chunks,
    publish_revision,
    store_revision_documents,
)


async def process_image_import(ctx: Any, task_id: str) -> dict[str, str]:
    from app.api import source_api
    from app.services import source_jobs

    try:
        async with source_jobs.async_session() as session:
            task = await session.get(SourceSyncTask, task_id)
            if task is None:
                return {"status": "cancelled"}
            source = (
                await session.execute(
                    select(Source)
                    .where(Source.id == task.source_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            await session.refresh(task)
            if task.status == "completed":
                return {"status": "completed"}
            if (
                source is None
                or source.deleted_at
                or source.archived_at
                or source.active_task_id != task_id
                or task.status != "pending"
            ):
                return {"status": "cancelled"}
            payload = dict(task.payload)
            source_id, owner_id = source.id, task.user_id
            task.status, task.stage = "processing", "parsing"
            await session.commit()
        path = Path(str(payload["file_path"])).resolve()
        if (
            not path.is_relative_to((source_api.SOURCE_ROOT / source_id).resolve())
            or not path.is_file()
        ):
            raise ValueError("Image original unavailable")
        validated = await asyncio.to_thread(image.validate_image, path)
        retained = cast(dict[str, Any], payload.get("manifest", {}))
        if retained and validated.image_hash != retained.get("image_hash"):
            raise ValueError("Image original integrity mismatch")
        if payload["operation"] == "edit":
            snapshot = image.build_image_snapshot(
                validated.image_hash,
                ocr_text=retained["ocr_text"],
                ocr_status=retained["ocr_status"],
                manual_description=str(payload["manual_description"]),
                ocr_correction=str(payload["ocr_correction"]),
                image_metadata=retained.get("image"),
            )
        else:
            snapshot = await asyncio.to_thread(
                image.collect_image,
                path,
                manual_description=str(payload["manual_description"]),
                ocr_correction=str(payload["ocr_correction"]),
            )
        pipeline = f"{image.PIPELINE_VERSION}:{settings.embedding_model}"
        chunks = document_chunks(snapshot.documents)
        async with source_jobs.async_session() as session:
            source = (
                await session.execute(
                    select(Source)
                    .where(Source.id == source_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            task = await session.get(SourceSyncTask, task_id)
            if (
                source is None
                or source.deleted_at
                or source.archived_at
                or task is None
                or task.status != "processing"
                or source.active_task_id != task_id
            ):
                return {"status": "cancelled"}
            revision = (
                await session.execute(
                    select(SourceRevision).where(
                        SourceRevision.source_id == source_id,
                        SourceRevision.raw_hash == snapshot.raw_hash,
                        SourceRevision.pipeline_version == pipeline,
                    )
                )
            ).scalar_one_or_none()
            if revision is None:
                revision = SourceRevision(
                    source_id=source_id,
                    raw_hash=snapshot.raw_hash,
                    pipeline_version=pipeline,
                    file_path=str(path),
                    filename=cast(str, payload["filename"]),
                    manifest={**snapshot.manifest, "needs_description": not bool(chunks)},
                )
                session.add(revision)
                await session.flush()
            ready = revision.state == "ready"
            if not ready:
                revision.state = "staging"
                await session.execute(
                    delete(KnowledgeItem).where(KnowledgeItem.revision_id == revision.id)
                )
                await session.execute(
                    delete(SourceDocument).where(SourceDocument.revision_id == revision.id)
                )
            revision_id = revision.id
            task.revision_id, task.stage = revision_id, "indexing"
            await session.commit()
        if len(chunks) > 10000:
            raise ValueError("Image chunk limit exceeded")
        vectors = (
            []
            if ready or not chunks
            else (await source_jobs.encode_texts([chunk.text for chunk in chunks])).tolist()
        )
        async with source_jobs.async_session() as session:
            await session.execute(
                select(User).where(User.id == owner_id).with_for_update(read=True, key_share=True)
            )
            baseline = await session.get(Source, source_id)
            if baseline is None or baseline.knowledge_base_id is None:
                return {"status": "cancelled"}
            kb = (
                await session.execute(
                    select(KnowledgeBase)
                    .where(
                        KnowledgeBase.id == baseline.knowledge_base_id,
                        KnowledgeBase.user_id == owner_id,
                    )
                    .with_for_update(read=True, key_share=True)
                )
            ).scalar_one_or_none()
            source = (
                await session.execute(
                    select(Source)
                    .where(Source.id == source_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            task = await session.get(SourceSyncTask, task_id)
            if task is not None:
                await session.refresh(task)
            if (
                kb is None
                or source is None
                or source.user_id != owner_id
                or source.deleted_at
                or source.archived_at
                or source.active_task_id != task_id
                or task is None
                or task.status != "processing"
            ):
                return {"status": "cancelled"}
            if source.current_revision_id != payload["expected_revision_id"]:
                raise ValueError("Image head changed")
            revision = await session.get(SourceRevision, revision_id)
            if revision is None:
                raise ValueError("Image revision unavailable")
            if not ready:
                await store_revision_documents(
                    session, source, revision, snapshot.documents, vectors
                )
            await publish_revision(session, source_id, revision_id, payload["expected_revision_id"])
            source.last_sync_manifest = revision.manifest
            task.status, task.stage = "completed", "published"
            source.active_task_id = None
            await session.commit()
    except asyncio.CancelledError:
        await asyncio.shield(source_jobs.mark_failed(task_id))
        raise
    except Exception:
        await source_jobs.mark_failed(task_id)
        return {"status": "failed"}
    await source_jobs.process_impact_events()
    return {"status": "completed"}
