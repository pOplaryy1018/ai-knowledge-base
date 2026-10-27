"""Authorize graph pointers against the current source and original documents."""

import asyncio
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import async_session
from app.models.graph_task import GraphBuildTask
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision
from app.models.source_publication import SourcePublication
from app.services.graph_store import GraphRelationPointer, list_projection_relations


async def _head(session: AsyncSession, source_id: str, user_id: str, *, lock: bool = False) -> tuple[str, str, str]:
    source_query = select(Source).where(
        Source.id == source_id, Source.user_id == user_id,
        Source.deleted_at.is_(None), Source.archived_at.is_(None))
    if lock:
        source_query = source_query.with_for_update()
    source = (await session.execute(source_query)).scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "资料来源不可用")
    if not source.current_revision_id or not source.current_publication_id:
        raise HTTPException(409, "资料尚未发布")
    revision = await session.get(SourceRevision, source.current_revision_id)
    publication = await session.get(SourcePublication, source.current_publication_id)
    if (revision is None or revision.source_id != source.id or revision.state != "ready"
            or publication is None or publication.source_id != source.id or publication.revision_id != revision.id):
        raise HTTPException(409, "当前发布版本不可用")
    task_query = select(GraphBuildTask).where(
        GraphBuildTask.source_id == source.id, GraphBuildTask.revision_id == revision.id,
        GraphBuildTask.user_id == user_id, GraphBuildTask.extractor_version == settings.graph_extractor_version,
        GraphBuildTask.status == "completed", GraphBuildTask.active_build_id.isnot(None))
    if lock:
        task_query = task_query.with_for_update()
    task = (await session.execute(task_query)).scalar_one_or_none()
    if task is None or task.active_build_id is None:
        raise HTTPException(409, "关系图谱尚未就绪")
    return revision.id, publication.id, task.active_build_id


def _safe_pointer(row: GraphRelationPointer) -> bool:
    labels = ((row.id, 200), (row.subject, 120), (row.subject_type, 60),
              (row.predicate, 120), (row.object, 120), (row.object_type, 60))
    if any(not isinstance(value, str) or not value.strip() or len(value) > maximum for value, maximum in labels):
        return False
    if type(row.quote_start) is not int or type(row.quote_end) is not int:
        return False
    try:
        uuid.UUID(row.item_id)
    except (ValueError, TypeError, AttributeError):
        return False
    return 0 <= row.quote_start < row.quote_end


async def list_source_relations(source_id: str, user_id: str, limit: int = 50) -> dict[str, Any]:
    if not 1 <= limit <= 50:
        raise ValueError("Graph relation limit must be between 1 and 50")
    async with async_session() as session:
        revision_id, publication_id, build_id = await _head(session, source_id, user_id)
    try:
        async with asyncio.timeout(5):
            candidates = await list_projection_relations(user_id, source_id, revision_id, build_id, limit + 1)
    except Exception:
        raise HTTPException(503, "关系图谱暂时不可用，请重试") from None

    selected = [row for row in candidates[:limit] if _safe_pointer(row)]
    async with async_session() as session:
        if await _head(session, source_id, user_id, lock=True) != (revision_id, publication_id, build_id):
            raise HTTPException(409, "资料或图谱已更新，请刷新后重试")
        ids = [str(uuid.UUID(row.item_id)) for row in selected]
        if not ids:
            return {"revision_id": revision_id, "items": [], "truncated": len(candidates) > limit}
        matches = (await session.execute(select(KnowledgeItem, SourceDocument)
            .join(SourceDocument, KnowledgeItem.document_id == SourceDocument.id)
            .where(KnowledgeItem.id.in_(ids), KnowledgeItem.revision_id == revision_id,
                   SourceDocument.revision_id == revision_id, KnowledgeItem.status == "available"))).all()
        items = {item.id: (item, document) for item, document in matches}
        output: list[dict[str, Any]] = []
        for row in selected:
            match = items.get(str(uuid.UUID(row.item_id)))
            if match is None:
                continue
            item, document = match
            start = (item.locator or {}).get("char_start")
            if (type(start) is not int or start < 0 or row.quote_end > len(item.content)
                    or document.text[start:start + len(item.content)] != item.content):
                continue
            quote = item.content[row.quote_start:row.quote_end]
            if row.subject not in quote or row.object not in quote:
                continue
            locator: dict[str, Any] = {}
            for key in ("page", "paragraph", "origin"):
                value = (item.locator or {}).get(key, (document.locator or {}).get(key))
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    locator[key] = value
            quote_start = start + row.quote_start
            quote_end = start + row.quote_end
            locator.update(logical_path=document.logical_path, char_start=quote_start, char_end=quote_end,
                           line_start=document.text.count("\n", 0, quote_start) + 1,
                           line_end=document.text.count("\n", 0, quote_end) + 1)
            output.append({"id": row.id, "subject": row.subject, "subject_type": row.subject_type,
                           "predicate": row.predicate, "object": row.object, "object_type": row.object_type,
                           "quote": quote, "document_id": document.id, "revision_id": revision_id, "locator": locator})
    return {"revision_id": revision_id, "items": output, "truncated": len(candidates) > limit}
