"""Durable ARQ ingestion; terminal rows and chunks commit together."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.file_types import CODE_EXTS
from app.services.import_tasks import finish_import, update_task
from app.services.parser import parse_file
from app.services.source_jobs import process_source_import, source_maintenance
from app.services.splitter import Chunk, split_text
from app.services.vectorizer import encode_texts, vectorize_chunks

logger = logging.getLogger(__name__)


async def split_import_text(text: str, path: str) -> list[Chunk]:
    extension = Path(path).suffix.lower()
    if extension not in CODE_EXTS:
        return await split_text(text, path)
    languages = {".py": Language.PYTHON, ".ts": Language.TS, ".tsx": Language.TS, ".js": Language.JS, ".jsx": Language.JS, ".java": Language.JAVA, ".go": Language.GO, ".rs": Language.RUST, ".c": Language.CPP, ".cpp": Language.CPP, ".h": Language.CPP}
    splitter = RecursiveCharacterTextSplitter.from_language(language=languages[extension], chunk_size=1000, chunk_overlap=150)
    return [Chunk(content=doc.page_content, index=index) for index, doc in enumerate(splitter.create_documents([text]))]


async def process_import(ctx: Any, task_id: str, file_id: str, kb_id: str, file_path: str, filename: str) -> dict[str, Any]:
    if not await update_task(task_id, claim=True, stage="parsing", message=f"正在解析: {filename}"):
        return {"status": "cancelled"}
    try:
        # OCR, subprocess conversion and PDF parsing are synchronous libraries.
        text = await asyncio.to_thread(lambda: asyncio.run(parse_file(file_path)))
        if not await update_task(task_id, stage="chunking", message="正在切分", percent=30):
            return {"status": "cancelled"}
        chunks = await split_import_text(text, file_path)
        if not chunks:
            raise ValueError("切分结果为空")
        if not await update_task(task_id, stage="vectorizing", message="正在向量化", percent=50):
            return {"status": "cancelled"}
        vectors = await vectorize_chunks(chunks)
        count = await finish_import(task_id, chunks, vectors, {"filename": filename, "file_type": Path(file_path).suffix.lstrip(".")})
        if count is None:
            return {"status": "cancelled"}
        return {"status": "ok", "total_chunks": count}
    except asyncio.CancelledError:
        await asyncio.shield(update_task(task_id, status="failed", error="任务超时或被取消，请重试"))
        raise
    except Exception as error:
        logger.exception("Import failed: %s", task_id)
        await update_task(task_id, status="failed", error=str(error))
        return {"status": "error", "error": str(error)}


async def on_worker_startup(ctx: Any) -> None:
    if settings.model_preload:
        await encode_texts(["模型预热"])


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_import, process_source_import]
    cron_jobs = [cron(source_maintenance, minute=set(range(60)), second=0)]
    on_startup = on_worker_startup
    max_jobs = 1
    job_timeout = 600
    keep_result = 3600
