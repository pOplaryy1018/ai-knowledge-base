"""Recoverable build and cleanup of the derived graph projection."""

import asyncio
import logging
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.models.graph_task import GraphBuildTask, GraphCleanup
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceRevision
from app.services.graph_extraction import ExtractionError, extract_relations
from app.services.graph_store import delete_build, delete_source, setup_schema, write_projection

logger = logging.getLogger(__name__)
LEASE = timedelta(minutes=10)


async def claim_graph_task(session: AsyncSession, task_id: str) -> GraphBuildTask | None:
    task = (await session.execute(select(GraphBuildTask).where(GraphBuildTask.id == task_id)
                                  .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if task is None or task.status != "pending":
        return None
    source = await session.get(Source, task.source_id)
    revision = await session.get(SourceRevision, task.revision_id)
    if source is None or source.deleted_at or revision is None or revision.state != "ready":
        task.status = "failed"
        task.error_code = "source_unavailable"
        await session.flush()
        return None
    task.status = "processing"
    task.attempts += 1
    task.lease_until = datetime.now(timezone.utc) + LEASE
    task.error_code = None
    await session.flush()
    return task


async def _mark_failed(task_id: str, attempt: int, code: str) -> None:
    async with async_session() as session:
        task = (await session.execute(select(GraphBuildTask).where(GraphBuildTask.id == task_id)
                                      .with_for_update())).scalar_one_or_none()
        if task and task.status == "processing" and task.attempts == attempt:
            task.status = "failed"
            task.error_code = code
            task.lease_until = None
            await session.commit()


async def process_graph_build(ctx: Any, task_id: str) -> dict[str, str]:
    del ctx
    async with async_session() as session:
        task = await claim_graph_task(session, task_id)
        if task is None:
            await session.commit()
            return {"status": "cancelled"}
        source_id, revision_id, user_id, attempt = task.source_id, task.revision_id, task.user_id, task.attempts
        active_build = task.active_build_id
        await session.commit()
    build_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"graph:{task_id}:{attempt}"))
    try:
        async with asyncio.timeout(540):
            if attempt > 1:
                previous = str(uuid.uuid5(uuid.NAMESPACE_URL, f"graph:{task_id}:{attempt - 1}"))
                if previous != active_build:
                    await delete_build(previous)
            async with async_session() as session:
                chunks = (await session.execute(select(KnowledgeItem).where(
                    KnowledgeItem.revision_id == revision_id, KnowledgeItem.status == "available")
                    .order_by(KnowledgeItem.id))).scalars().all()
            result = await extract_relations(chunks)
            await setup_schema()
            await write_projection(build_id, user_id, source_id, revision_id, result.relations)
            async with async_session() as session:
                task = (await session.execute(select(GraphBuildTask).where(GraphBuildTask.id == task_id)
                                              .with_for_update())).scalar_one_or_none()
                source = await session.get(Source, source_id)
                if task is None or source is None or source.deleted_at or task.attempts != attempt or task.status != "processing":
                    raise RuntimeError("source_unavailable")
                task.active_build_id = build_id
                task.status = "completed"
                task.lease_until = None
                task.relation_count = len(result.relations)
                task.rejected_count = result.rejected_count
                task.error_code = None
                await session.commit()
        return {"status": "completed"}
    except asyncio.CancelledError:
        await asyncio.shield(_mark_failed(task_id, attempt, "cancelled"))
        raise
    except Exception as error:
        code = str(error) if isinstance(error, ExtractionError) else "graph_unavailable"
        logger.warning("Graph build failed for task %s (%s)", task_id, code)
        await _mark_failed(task_id, attempt, code[:80])
        with suppress(Exception):
            await delete_build(build_id)
        return {"status": "failed"}


async def recover_graph_tasks(session: AsyncSession) -> list[tuple[str, int]]:
    """Return pending IDs and next-attempt keys after recovering expired leases."""
    await session.execute(update(GraphBuildTask).where(
        GraphBuildTask.status == "processing", GraphBuildTask.lease_until < datetime.now(timezone.utc))
        .values(status="pending", lease_until=None))
    rows = (await session.execute(select(GraphBuildTask.id, GraphBuildTask.attempts)
                                  .where(GraphBuildTask.status == "pending")
                                  .order_by(GraphBuildTask.created_at, GraphBuildTask.id).limit(20))).all()
    return [(task_id, attempts + 1) for task_id, attempts in rows]


async def process_graph_cleanup(session: AsyncSession) -> None:
    intents = (await session.execute(select(GraphCleanup).where(GraphCleanup.status == "pending")
                                     .order_by(GraphCleanup.created_at).limit(20))).scalars().all()
    targets = [(intent.id, intent.user_id, intent.source_id) for intent in intents]
    for cleanup_id, user_id, source_id in targets:
        try:
            await delete_source(user_id, source_id)
        except Exception:
            logger.warning("Graph cleanup will retry for source %s", source_id)
            continue
        intent = await session.get(GraphCleanup, cleanup_id)
        if intent is not None:
            await session.delete(intent)
