"""向量化引擎 ── BGE-M3 嵌入模型 + pgvector 存储"""

import logging
from typing import Any, Sequence

import numpy as np
from sqlalchemy import select

from app.core.db import async_session
from app.models.knowledge import EMBEDDING_DIM, KnowledgeItem
from app.services.splitter import Chunk

logger = logging.getLogger(__name__)

# ── 全局模型缓存 ──
_model: Any = None


def get_model() -> Any:
    """加载 Qwen3-Embedding-0.6B 模型（懒加载 + 全局缓存，从 ModelScope 下载到 E 盘）"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("正在从 ModelScope 下载 Qwen3-Embedding-0.6B 模型到 E 盘...")
        from modelscope import snapshot_download

        model_dir = snapshot_download(
            "Qwen/Qwen3-Embedding-0.6B",
            cache_dir="E:/ai-models",
        )
        logger.info("模型下载完成，正在加载到内存...")
        _model = SentenceTransformer(model_dir, trust_remote_code=True)
        logger.info("Qwen3-Embedding-0.6B 模型加载完成")
    return _model


async def vectorize_chunks(chunks: list[Chunk]) -> list[list[float]]:
    """将文本片段向量化（BGE-M3 1024 维）"""
    model = get_model()
    texts: list[str] = [chunk.content for chunk in chunks]

    # BGE-M3 可直接调用 encode 返回 1024 维向量
    embeddings: Any = model.encode(
        texts,
        normalize_embeddings=True,  # 余弦相似度需归一化
        show_progress_bar=False,
    )

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
) -> int:
    """将切分后的文本片段及向量写入 knowledge_items 表"""
    async with async_session() as session:
        count: int = 0
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
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
        await session.commit()
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
