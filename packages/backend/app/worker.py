"""ARQ Worker ── 异步文档处理任务

启动: arq app.worker.WorkerSettings
"""
from __future__ import annotations

import json
import logging
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from arq.worker import create_worker

from app.core.config import settings
from app.services.parser import parse_file
from app.services.splitter import Chunk, split_text
from app.services.vectorizer import store_chunks, vectorize_chunks

logger = logging.getLogger(__name__)


async def publish_progress(ctx: Any, task_id: str, stage: str, message: str, percent: int) -> None:
    """向 Redis Pub/Sub 频道发布进度事件"""
    channel: str = f"import_progress:{task_id}"
    payload: dict[str, Any] = {
        "type": "progress",
        "stage": stage,
        "message": message,
        "percent": percent,
    }
    await ctx["redis"].publish(channel, json.dumps(payload, ensure_ascii=False))


async def publish_complete(ctx: Any, task_id: str, kb_id: str, total_chunks: int, preview: list[dict[str, Any]]) -> None:
    """向 Redis Pub/Sub 频道发布完成事件"""
    channel: str = f"import_progress:{task_id}"
    payload: dict[str, Any] = {
        "type": "complete",
        "total_chunks": total_chunks,
        "kb_id": kb_id,
        "preview": preview,
    }
    await ctx["redis"].publish(channel, json.dumps(payload, ensure_ascii=False))


async def publish_error(ctx: Any, task_id: str, error_msg: str) -> None:
    """向 Redis Pub/Sub 频道发布错误事件"""
    channel: str = f"import_progress:{task_id}"
    payload: dict[str, str] = {"type": "error", "error": error_msg}
    await ctx["redis"].publish(channel, json.dumps(payload, ensure_ascii=False))


async def process_import(
    ctx: Any,
    task_id: str,
    file_id: str,
    kb_id: str,
    file_path: str,
    filename: str,
) -> dict[str, Any]:
    """文档导入主流程：解析 → 切分 → 向量化 → 入库"""
    from pathlib import Path

    from app.core.db import async_session
    from app.models.knowledge import KnowledgeFile
    from sqlalchemy import select

    suffix = Path(file_path).suffix.lower()

    async def update_file_status(status: str, **kwargs: Any) -> None:
        """更新 KnowledgeFile 状态"""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(KnowledgeFile).where(KnowledgeFile.id == file_id)
                )
                kf = result.scalar_one_or_none()
                if kf:
                    kf.status = status
                    for key, value in kwargs.items():
                        setattr(kf, key, value)
                    await session.commit()
        except Exception:
            logger.exception("更新文件状态失败")

    try:
        # 更新状态为 processing
        await update_file_status("processing")

        # ── 阶段 1: 解析文本 (0-25%) ──
        await publish_progress(ctx, task_id, "parsing", f"正在解析: {filename}", 0)

        text = await parse_file(file_path)

        if not text.strip():
            raise ValueError("文件解析结果为空，请检查文件是否包含可提取的文字内容")
        await publish_progress(ctx, task_id, "parsing", "文档解析完成", 25)

        # ── 阶段 2: 切分段落 (25-50%) ──
        await publish_progress(ctx, task_id, "chunking", "正在切分段落...", 30)

        code_exts = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs",
            ".c", ".cpp", ".h",
        }
        if suffix in code_exts:
            from app.services.splitter import Chunk
            from langchain_text_splitters import RecursiveCharacterTextSplitter, Language

            lang_map: dict[str, Any] = {
                ".py": Language.PYTHON, ".ts": Language.TS, ".tsx": Language.TS,
                ".js": Language.JS, ".jsx": Language.JS, ".java": Language.JAVA,
                ".go": Language.GO, ".rs": Language.RUST, ".c": Language.CPP,
                ".cpp": Language.CPP, ".h": Language.CPP,
            }
            lang = lang_map.get(suffix, Language.PYTHON)
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=lang, chunk_size=1000, chunk_overlap=150,
            )
            docs = splitter.create_documents([text])
            chunks = [
                Chunk(title="", content=doc.page_content, metadata={})
                for doc in docs
            ]
        else:
            chunks = await split_text(text, file_path)

        if not chunks:
            raise ValueError("切分结果为空")
        await publish_progress(ctx, task_id, "chunking", f"切分完成，生成 {len(chunks)} 个片段", 50)

        # ── 阶段 3: 向量化 (50-85%) ──
        await publish_progress(ctx, task_id, "vectorizing", "正在加载 BGE-M3 模型并向量化...", 55)
        vectors: list[list[float]] = await vectorize_chunks(chunks)
        await publish_progress(ctx, task_id, "vectorizing", f"向量化完成 ({len(vectors)} 条)", 85)

        # ── 阶段 4: 入库 (85-100%) ──
        await publish_progress(ctx, task_id, "storing", "正在写入数据库...", 90)
        stored_count: int = await store_chunks(
            kb_id, chunks, vectors,
            source="file_import",
            file_id=file_id,
            source_metadata_base={
                "filename": filename,
                "file_type": suffix.lstrip("."),
            },
        )
        await publish_progress(ctx, task_id, "storing", "写入完成", 100)

        # 更新文件状态为 completed
        await update_file_status("completed", chunks_count=stored_count)

        # ── 发送完成事件 ──
        preview: list[dict[str, Any]] = [
            {"title": ch.title or ch.content[:50], "content_preview": ch.content[:200]}
            for ch in chunks[:10]
        ]
        await publish_complete(ctx, task_id, kb_id, stored_count, preview)
        logger.info("导入完成: task_id=%s, kb_id=%s, chunks=%d", task_id, kb_id, stored_count)

        return {"status": "ok", "total_chunks": stored_count}

    except Exception as e:
        logger.exception("导入失败: %s", e)
        await publish_error(ctx, task_id, str(e))
        await update_file_status("failed", error_message=str(e))
        return {"status": "error", "error": str(e)}


# ── ARQ Worker 配置 ──


ARQ_REDIS_SETTINGS: RedisSettings = RedisSettings.from_dsn(settings.redis_url)

# Worker 启动时加载 BGE-M3 模型（预加载，避免每次推理加载模型）
async def on_worker_startup(ctx: Any) -> None:
    """Worker 启动回调：预加载 BGE-M3 模型"""
    logger.info("Worker 启动中，正在预加载 BGE-M3 模型...")
    from app.services.vectorizer import get_model

    get_model()
    logger.info("Worker 启动完成，模型已就绪")


class WorkerSettings:
    """ARQ Worker 配置类"""
    redis_settings: RedisSettings = ARQ_REDIS_SETTINGS
    functions: list[Any] = [process_import]
    on_startup: Any = on_worker_startup
    max_jobs: int = 1  # BGE-M3 推理耗内存，每次只跑一个任务
    job_timeout: int = 600  # 单任务超时 10 分钟
    keep_result: int = 3600  # 结果保留 1 小时
