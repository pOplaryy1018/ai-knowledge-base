"""向量化引擎 ── 可配置嵌入模型 + pgvector 存储"""

import asyncio
import logging
from typing import Any, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import async_session
from app.models.knowledge import EMBEDDING_DIM, KnowledgeItem
from app.services.splitter import Chunk

logger = logging.getLogger(__name__)

# ── 全局模型缓存 ──
_model: Any = None
_encoding_lock = asyncio.Lock()


async def encode_texts(texts: Any) -> Any:
    """Bound concurrent inference and keep synchronous model work off the API loop."""
    async with _encoding_lock:
        inference = asyncio.create_task(asyncio.to_thread(
            lambda: get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
        ))
        try:
            return await asyncio.shield(inference)
        except asyncio.CancelledError:
            # A cancelled await cannot stop its worker thread. Keep the lock until it exits.
            cleanup = asyncio.gather(inference, return_exceptions=True)
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            raise


def get_model() -> Any:
    """从 ModelScope 加载配置的模型，缓存到可写目录。"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("正在从 ModelScope 加载模型 %s...", settings.embedding_model)
        from modelscope import snapshot_download

        model_dir = snapshot_download(
            settings.embedding_model,
            cache_dir=settings.embedding_cache_dir,
        )
        logger.info("模型下载完成，正在加载到内存...")
        _model = SentenceTransformer(model_dir, trust_remote_code=False)
        logger.info("Embedding 模型加载完成")
    return _model


async def vectorize_chunks(chunks: list[Chunk]) -> list[list[float]]:
    """将文本片段向量化并验证数据库要求的维度。"""
    texts: list[str] = [chunk.content for chunk in chunks]

    embeddings: Any = await encode_texts(texts)

    if isinstance(embeddings, np.ndarray):
        result: list[list[float]] = embeddings.tolist()
    else:
        result = [e.tolist() for e in embeddings]

    # 校验维度
    for vec in result:
        if len(vec) != EMBEDDING_DIM:
            raise ValueError(f"向量维度不匹配: 期望 {EMBEDDING_DIM}，实际 {len(vec)}")

    return result


async def store_chunks(
    kb_id: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    source: str = "file_import",
    file_id: str | None = None,
    source_metadata_base: dict[str, object] | None = None,
    session: AsyncSession | None = None,
) -> int:
    """将切分后的文本片段及向量写入 knowledge_items 表"""
    if len(chunks) != len(vectors):
        raise ValueError("Chunk and embedding counts must match")
    if session is None:
        async with async_session() as owned:
            stored_count = await store_chunks(kb_id, chunks, vectors, source, file_id, source_metadata_base, owned)
            await owned.commit()
            return stored_count
    else:
        count: int = 0
        for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=True)):
            meta: dict[str, object] = dict(source_metadata_base or {})
            meta["chunk_index"] = i

            item: KnowledgeItem = KnowledgeItem(
                knowledge_base_id=kb_id,
                file_id=file_id,
                title=chunk.title or chunk.content[:80],
                content=chunk.content,
                type="document",
                source=source,
                source_metadata=meta,
                embedding=vec,
            )
            session.add(item)
            count += 1
    return count


async def search_similar(
    kb_id: str,
    query_vector: list[float],
    top_k: int = 5,
) -> Sequence[KnowledgeItem]:
    """向量相似度检索（pgvector 余弦距离）"""
    async with async_session() as session:
        # 按余弦距离排序（越小越相似）
        result = await session.execute(
            select(KnowledgeItem)
            .where(
                KnowledgeItem.knowledge_base_id == kb_id,
                KnowledgeItem.status == "available",
                KnowledgeItem.embedding.isnot(None),
            )
            .order_by(KnowledgeItem.embedding.cosine_distance(query_vector))
            .limit(top_k)
        )
        return result.scalars().all()
