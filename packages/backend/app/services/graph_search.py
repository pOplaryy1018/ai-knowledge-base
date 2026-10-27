"""Merge pgvector/keyword retrieval with authorized graph evidence pointers."""

import asyncio
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.db import async_session
from app.models.graph_task import GraphBuildTask
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision
from app.services.graph_store import find_candidate_chunk_ids
from app.services.search_service import SearchResult, hybrid_search_versions

logger = logging.getLogger(__name__)


async def _graph_results(versions: dict[str, str], question: str, user_id: str,
                         limit: int) -> list[SearchResult]:
    if not versions:
        return []
    selected = [and_(GraphBuildTask.source_id == source_id, GraphBuildTask.revision_id == revision_id)
                for source_id, revision_id in versions.items()]
    async with async_session() as session:
        tasks = (await session.execute(select(GraphBuildTask)
            .join(Source, GraphBuildTask.source_id == Source.id)
            .join(SourceRevision, GraphBuildTask.revision_id == SourceRevision.id)
            .where(GraphBuildTask.user_id == user_id,
                   GraphBuildTask.extractor_version == settings.graph_extractor_version,
                   GraphBuildTask.status == "completed", GraphBuildTask.active_build_id.isnot(None),
                   Source.user_id == user_id, Source.deleted_at.is_(None), Source.archived_at.is_(None),
                   SourceRevision.state == "ready", or_(*selected)))).scalars().all()
    builds = {task.revision_id: task.active_build_id for task in tasks if task.active_build_id}
    if not builds:
        return []
    candidates = await find_candidate_chunk_ids(user_id, builds, question, limit)
    if not candidates:
        return []
    ids = [candidate.item_id for candidate in candidates]
    allowed = [and_(Source.id == source_id, SourceRevision.id == revision_id)
               for source_id, revision_id in versions.items()]
    async with async_session() as session:
        rows = (await session.execute(select(KnowledgeItem, Source.id)
            .join(SourceDocument, KnowledgeItem.document_id == SourceDocument.id)
            .join(SourceRevision, KnowledgeItem.revision_id == SourceRevision.id)
            .join(Source, SourceRevision.source_id == Source.id)
            .where(KnowledgeItem.id.in_(ids), KnowledgeItem.status == "available",
                   SourceDocument.revision_id == SourceRevision.id,
                   Source.user_id == user_id, Source.deleted_at.is_(None), Source.archived_at.is_(None),
                   SourceRevision.state == "ready", or_(*allowed)))).all()
    items = {item.id: (item, source_id) for item, source_id in rows}
    results: list[SearchResult] = []
    seen: set[str] = set()
    for candidate in candidates:
        match = items.get(candidate.item_id)
        if (match is None or candidate.item_id in seen or match[1] != candidate.source_id
                or match[0].revision_id != candidate.revision_id
                or builds.get(candidate.revision_id) != candidate.build_id):
            continue
        seen.add(candidate.item_id)
        results.append(SearchResult(match[0], 1 / (60 + candidate.route_rank)))
    return results


async def retrieve_version_evidence(versions: dict[str, str], question: str,
                                    user_id: str, top_k: int = 5,
                                    embedding_task: asyncio.Task[Any] | None = None) -> list[SearchResult]:
    if not versions:
        return []
    vector_search = (hybrid_search_versions(versions, question, top_k=top_k * 3, user_id=user_id,
                                            embedding_task=embedding_task)
                     if embedding_task else hybrid_search_versions(versions, question, top_k=top_k * 3, user_id=user_id))
    vector_route = asyncio.wait_for(vector_search, timeout=30)
    graph_route = asyncio.wait_for(_graph_results(versions, question, user_id, top_k * 3), timeout=5)
    vector, graph = await asyncio.gather(vector_route, graph_route, return_exceptions=True)
    if isinstance(vector, BaseException) and isinstance(graph, BaseException):
        raise HTTPException(503, "检索服务暂时不可用，请稍后重试")
    if isinstance(graph, BaseException):
        logger.warning("Graph retrieval unavailable; using source search")
        graph = []
    if isinstance(vector, BaseException):
        logger.warning("Source search unavailable; using graph evidence")
        if not graph:
            raise HTTPException(503, "检索服务暂时不可用，请稍后重试")
        vector = []
    combined: dict[str, SearchResult] = {}
    for result in vector:
        combined[result.item.id] = SearchResult(result.item, result.score * 0.5,
                                                 result.dense_score, result.sparse_score)
    for result in graph:
        if result.item.id in combined:
            combined[result.item.id].score += result.score * 0.5
        else:
            combined[result.item.id] = SearchResult(result.item, result.score * 0.5)
    ranked = sorted(combined.values(), key=lambda result: (-result.score, result.item.id))
    source_for_revision = {revision_id: source_id for source_id, revision_id in versions.items()}
    per_source_limit = top_k if len(versions) == 1 else max(2, (top_k + len(versions) - 1) // len(versions))
    by_source: dict[str, int] = {}
    output: list[SearchResult] = []
    for result in ranked:
        source_id = source_for_revision.get(result.item.revision_id or "", "")
        if by_source.get(source_id, 0) >= per_source_limit:
            continue
        by_source[source_id] = by_source.get(source_id, 0) + 1
        output.append(result)
        if len(output) >= top_k:
            break
    return output
