"""Authorized independent dense/keyword retrieval with reciprocal rank fusion."""

from dataclasses import dataclass

import jieba
from sqlalchemy import case, literal, or_, select

from app.core.db import async_session
from app.models.knowledge import KnowledgeBase, KnowledgeItem
from app.services.vectorizer import encode_texts


@dataclass
class SearchResult:
    item: KnowledgeItem
    score: float
    dense_score: float = 0.0
    sparse_score: float = 0.0


def _extract_keywords(query: str, top_n: int = 10) -> list[str]:
    stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "怎么", "如何", "为什么", "什么", "可以", "没有"}
    return list(dict.fromkeys(word for word in jieba.lcut(query) if len(word) > 1 and word not in stop_words))[:top_n]


async def hybrid_search(knowledge_ids: list[str], query: str, top_k: int = 5, dense_weight: float = 0.5, *, user_id: str, is_admin: bool = False) -> list[SearchResult]:
    if not knowledge_ids:
        return []
    vector = (await encode_texts(query)).tolist()
    filters = [KnowledgeItem.id.in_(knowledge_ids), KnowledgeItem.status == "available"]
    if not is_admin:
        filters.append(KnowledgeBase.user_id == user_id)
    results: dict[str, SearchResult] = {}
    async with async_session() as session:
        dense = await session.execute(
            select(KnowledgeItem, (1 - KnowledgeItem.embedding.cosine_distance(vector)).label("score"))
            .join(KnowledgeBase, KnowledgeItem.knowledge_base_id == KnowledgeBase.id)
            .where(*filters, KnowledgeItem.embedding.isnot(None))
            .order_by(KnowledgeItem.embedding.cosine_distance(vector), KnowledgeItem.id)
            .limit(top_k * 3)
        )
        for rank, row in enumerate(dense.all(), start=1):
            item, similarity = row[0], float(row[1])
            results[item.id] = SearchResult(item, dense_weight / (60 + rank), dense_score=similarity)
        keywords = _extract_keywords(query)
        if keywords:
            matches = [or_(KnowledgeItem.title.ilike(f"%{word}%"), KnowledgeItem.content.ilike(f"%{word}%")) for word in keywords]
            match_score = sum((case((condition, 1), else_=0) for condition in matches), start=literal(0))
            sparse = await session.execute(
                select(KnowledgeItem).join(KnowledgeBase, KnowledgeItem.knowledge_base_id == KnowledgeBase.id)
                .where(*filters, or_(*matches)).order_by(match_score.desc(), KnowledgeItem.id).limit(top_k * 3)
            )
            for rank, item in enumerate(sparse.scalars().all(), start=1):
                if item.id not in results:
                    results[item.id] = SearchResult(item, 0.0)
                results[item.id].score += (1 - dense_weight) / (60 + rank)
                results[item.id].sparse_score = 1 / rank
    return sorted(results.values(), key=lambda result: (-result.score, result.item.id))[:top_k]


async def hybrid_search_versions(versions: dict[str, str], query: str, top_k: int = 5, dense_weight: float = 0.5, *, user_id: str) -> list[SearchResult]:
    """Retrieve only authorized immutable source/document version pairs."""
    from sqlalchemy import and_

    from app.models.source import Source, SourceDocument, SourceRevision

    if not versions:
        return []
    vector = (await encode_texts(query)).tolist()
    base = (select(KnowledgeItem)
            .join(SourceDocument, KnowledgeItem.document_id == SourceDocument.id)
            .join(SourceRevision, KnowledgeItem.revision_id == SourceRevision.id)
            .join(Source, SourceRevision.source_id == Source.id)
            .where(SourceDocument.revision_id == SourceRevision.id,
                   Source.user_id == user_id, Source.archived_at.is_(None), Source.deleted_at.is_(None),
                   SourceRevision.state == "ready", KnowledgeItem.status == "available",
                   or_(*(and_(Source.id == source, SourceRevision.id == revision) for source, revision in versions.items()))))
    results: dict[str, SearchResult] = {}
    async with async_session() as session:
        dense = await session.execute(base.add_columns((1 - KnowledgeItem.embedding.cosine_distance(vector)).label("score"))
                                      .where(KnowledgeItem.embedding.isnot(None))
                                      .order_by(KnowledgeItem.embedding.cosine_distance(vector), KnowledgeItem.id).limit(top_k * 3))
        for rank, row in enumerate(dense.all(), 1):
            results[row[0].id] = SearchResult(row[0], dense_weight / (60 + rank), dense_score=float(row[1]))
        keywords = _extract_keywords(query)
        if keywords:
            matches = [or_(KnowledgeItem.title.ilike(f"%{word}%"), KnowledgeItem.content.ilike(f"%{word}%")) for word in keywords]
            score = sum((case((match, 1), else_=0) for match in matches), start=literal(0))
            sparse = await session.execute(base.where(or_(*matches)).order_by(score.desc(), KnowledgeItem.id).limit(top_k * 3))
            for rank, item in enumerate(sparse.scalars().all(), 1):
                results.setdefault(item.id, SearchResult(item, 0.0)).score += (1 - dense_weight) / (60 + rank)
                results[item.id].sparse_score = 1 / rank
    return sorted(results.values(), key=lambda result: (-result.score, result.item.id))[:top_k]
