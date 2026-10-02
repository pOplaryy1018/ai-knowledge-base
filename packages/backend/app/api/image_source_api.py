"""Durable, owner scoped image revision requests."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api import source_api
from app.core.security import get_current_user
from app.models.knowledge import KnowledgeBase
from app.models.source import SourceRevision, SourceSyncTask
from app.models.user import User
from app.services.connectors.image import MAX_IMAGE_BYTES, validate_image
from app.services.connectors.types import ConnectorError, SnapshotLimitError

router = APIRouter(tags=["图片来源"])


class ImageText(BaseModel):
    expected_revision_id: uuid.UUID
    manual_description: str = Field(default="", max_length=100000)
    ocr_correction: str = Field(default="", max_length=100000)


class ImageReextract(BaseModel):
    expected_revision_id: uuid.UUID


async def queue_image(
    source_id: str, user: User, expected: str | None, payload: dict[str, Any]
) -> dict[str, Any]:
    async with source_api.async_session() as session:
        await session.execute(
            select(User).where(User.id == user.id).with_for_update(read=True, key_share=True)
        )
        baseline = await source_api.owned_source(session, source_id, user.id)
        kb = (
            await session.execute(
                select(KnowledgeBase)
                .where(
                    KnowledgeBase.id == baseline.knowledge_base_id, KnowledgeBase.user_id == user.id
                )
                .with_for_update(read=True, key_share=True)
            )
        ).scalar_one_or_none()
        source = await source_api.owned_source(session, source_id, user.id, lock=True)
        if kb is None:
            raise HTTPException(404, "知识库不存在")
        if source.kind != "image":
            raise HTTPException(422, "仅支持图片来源")
        if source.archived_at or source.active_task_id:
            raise HTTPException(409, "来源已归档或已有同步任务")
        if source.current_revision_id != expected:
            raise HTTPException(409, "资料版本已变化")
        if payload["operation"] != "upload":
            revision = await session.get(SourceRevision, expected)
            if (
                revision is None
                or revision.source_id != source.id
                or revision.state != "ready"
                or not revision.file_path
            ):
                raise HTTPException(409, "图片版本不可用")
            payload = {
                **payload,
                "file_path": revision.file_path,
                "filename": revision.filename,
                "manifest": revision.manifest,
            }
            if payload["operation"] == "reextract":
                payload.update(
                    manual_description=revision.manifest.get("manual_description", ""),
                    ocr_correction=revision.manifest.get("ocr_correction", ""),
                )
        task = SourceSyncTask(
            source_id=source.id,
            user_id=user.id,
            payload={**payload, "expected_revision_id": expected},
        )
        session.add(task)
        await session.flush()
        source.active_task_id = task.id
        await session.commit()
    try:
        from app.api.import_api import get_arq

        await (await get_arq()).enqueue_job(
            "process_source_import", task.id, _job_id=f"source:{task.id}"
        )
    except Exception:
        pass
    return {"source_id": source_id, "revision_id": None, "task_id": task.id, "status": task.status}


@router.post("/sources/{source_id}/image-revisions", status_code=202)
async def upload_image(
    source_id: uuid.UUID,
    file: UploadFile,
    expected_revision_id: uuid.UUID | None = Form(default=None),
    manual_description: str = Form(default="", max_length=100000),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with source_api.async_session() as session:
        await source_api.owned_source(session, str(source_id), user.id)
    filename = Path((file.filename or "").replace("\\", "/")).name
    directory = source_api.SOURCE_ROOT / str(source_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4()}{Path(filename).suffix.lower()}"
    keep = False
    try:
        total = 0
        with path.open("wb") as output:
            while data := await file.read(1024 * 1024):
                total += len(data)
                if total > MAX_IMAGE_BYTES:
                    raise HTTPException(413, "图片超过大小限制")
                output.write(data)
        try:
            await asyncio.to_thread(validate_image, path)
        except SnapshotLimitError as error:
            raise HTTPException(413, "图片超过大小限制") from error
        except ConnectorError as error:
            raise HTTPException(422, "无效的图片格式") from error
        result = await queue_image(
            str(source_id),
            user,
            str(expected_revision_id) if expected_revision_id else None,
            {
                "operation": "upload",
                "file_path": str(path),
                "filename": filename,
                "manual_description": manual_description,
                "ocr_correction": "",
            },
        )
        keep = True
        return result
    finally:
        if not keep:
            path.unlink(missing_ok=True)


@router.patch("/sources/{source_id}/image-text", status_code=202)
async def edit_image(
    source_id: uuid.UUID, body: ImageText, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return await queue_image(
        str(source_id),
        user,
        str(body.expected_revision_id),
        {
            "operation": "edit",
            "manual_description": body.manual_description,
            "ocr_correction": body.ocr_correction,
        },
    )


@router.post("/sources/{source_id}/image-reextract", status_code=202)
async def reextract_image(
    source_id: uuid.UUID, body: ImageReextract, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return await queue_image(
        str(source_id), user, str(body.expected_revision_id), {"operation": "reextract"}
    )
