"""混合检索引擎 ── 稠密向量 + 稀疏关键词"""

import logging
from dataclasses import dataclass, field

import jieba
from sqlalchemy import or_, select, text
from sqlalchemy.sql import func

from app.core.db import async_session
from app.models.knowledge import KnowledgeItem
from app.services.vectorizer import get_model

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """检索结果"""
    item: KnowledgeItem
    score: float
    dense_score: float = 0.0
    sparse_score: float = 0.0


def _extract_keywords(query: str, top_n: int = 10) -> list[str]:
    """使用 jieba 提取关键词"""
    words = jieba.lcut(query)
    # 停用词过滤
    stop_words = {"的", "了", "在", "是", "我", "有", "和", "就",
                  "不", "人", "都", "一", "一个", "上", "也", "很",
                  "到", "说", "要", "去", "你", "会", "着", "没有",
                  "看", "好", "自己", "这", "他", "她", "它", "们",
                  "那", "什么", "怎么", "如何", "为什么", "可以",
                  "吗", "呢", "啊", "吧", "哦", "嗯", "哈", "呀"}
    keywords = [w for w in words if len(w) > 1 and w not in stop_words]
    # 去重并保留前 top_n
    seen: set[str] = set()
    result: list[str] = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result[:top_n]


async def hybrid_search(
    knowledge_ids: list[str],
    query: str,
    top_k: int = 5,
    dense_weight: float = 0.7,
) -> list[SearchResult]:
    """混合检索 ── 向量检索 + 关键词匹配，加权合并"""
    if not knowledge_ids:
        return []

    model = get_model()

    # 1. 稠密向量检索：取 top_k * 3 候选
    query_vector = model.encode(
        query,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()

    async with async_session() as session:
        dense_result = await session.execute(
            select(
                KnowledgeItem,
                (1 - KnowledgeItem.embedding.cosine_distance(query_vector)).label("score"),
            )
            .where(
                KnowledgeItem.id.in_(knowledge_ids),
                KnowledgeItem.status == "available",
                KnowledgeItem.embedding.isnot(None),
            )
            .order_by(KnowledgeItem.embedding.cosine_distance(query_vector))
            .limit(top_k * 3)
        )
        dense_results: dict[str, SearchResult] = {}
        for row in dense_result.all():
            item = row[0]
            score = float(row.score)
            dense_results[item.id] = SearchResult(
                item=item, score=score * dense_weight,
                dense_score=score, sparse_score=0.0,
            )

        # 2. 稀疏关键词检索
        keywords = _extract_keywords(query)
        if keywords and len(dense_results) < top_k:
            keyword_conditions = []
            for kw in keywords:
                keyword_conditions.append(KnowledgeItem.title.ilike(f"%{kw}%"))
                keyword_conditions.append(KnowledgeItem.content.ilike(f"%{kw}%"))
            # 也搜索不在 dense_results 中的条目
            keyword_result = await session.execute(
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.id.in_(knowledge_ids),
                    KnowledgeItem.status == "available",
                    KnowledgeItem.embedding.isnot(None),
                    or_(*keyword_conditions),
                )
                .limit(top_k * 2)
            )
            for item in keyword_result.scalars().all():
                match_count = sum(
                    1 for kw in keywords
                    if kw in item.title or kw in item.content
                )
                sparse_score = min(match_count / max(len(keywords), 1), 1.0)
                if item.id in dense_results:
                    sr = dense_results[item.id]
                    sr.sparse_score = sparse_score
                    sr.score += sparse_score * (1 - dense_weight)
                else:
                    dense_results[item.id] = SearchResult(
                        item=item,
                        score=sparse_score * (1 - dense_weight),
                        dense_score=0.0,
                        sparse_score=sparse_score,
                    )

    # 按综合分数排序
    sorted_results = sorted(
        dense_results.values(),
        key=lambda r: r.score,
        reverse=True,
    )
    return sorted_results[:top_k]
