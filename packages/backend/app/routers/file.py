"""文件管理路由 ── 列表 / 删除 / 重试 / 预览"""

import mimetypes
import os
import uuid
from pathlib import Path
from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.core.db import async_session
from app.core.security import get_current_user, require_super_admin
from app.models.knowledge import KnowledgeBase, KnowledgeFile, KnowledgeItem
from app.models.user import User
from app.schemas.knowledge import KnowledgeFileListResponse, KnowledgeFileResponse
from app.schemas.import_schema import FileRetryResponse

router: APIRouter = APIRouter(tags=["文件管理"])


def verify_file_access(kf: KnowledgeFile, user: User) -> None:
    """校验文件访问权限（owner 或 super_admin）"""
    if user.role != "super_admin" and kf.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该文件")


# ── 文件列表 ──

@router.get("/knowledge-bases/{kb_id}/files", response_model=KnowledgeFileListResponse)
async def list_files(
    kb_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="按文件名模糊搜索"),
    status_filter: str | None = Query(None, alias="status"),
    file_type: str | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: User = Depends(get_current_user),
) -> KnowledgeFileListResponse:
    """获取知识库下的文件列表（分页+搜索+筛选+排序）"""
    async with async_session() as session:
        kb_result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        if current_user.role != "super_admin" and kb.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该知识库")

        base_q = select(KnowledgeFile).where(KnowledgeFile.knowledge_base_id == kb_id)
        count_q = select(func.count(KnowledgeFile.id)).where(
            KnowledgeFile.knowledge_base_id == kb_id
        )

        if search:
            filter_clause = KnowledgeFile.original_filename.ilike(f"%{search}%")
            base_q = base_q.where(filter_clause)
            count_q = count_q.where(filter_clause)

        if status_filter:
            base_q = base_q.where(KnowledgeFile.status == status_filter)
            count_q = count_q.where(KnowledgeFile.status == status_filter)

        if file_type:
            base_q = base_q.where(KnowledgeFile.file_type == file_type)
            count_q = count_q.where(KnowledgeFile.file_type == file_type)

        total_result = await session.execute(count_q)
        total: int = total_result.scalar() or 0

        sort_col = getattr(KnowledgeFile, sort_by, KnowledgeFile.created_at)
        order = sort_col.desc() if sort_order == "desc" else sort_col.asc()

        offset = (page - 1) * size
        result = await session.execute(
            base_q.order_by(order).offset(offset).limit(size)
        )
        files: Sequence[KnowledgeFile] = result.scalars().all()

        return KnowledgeFileListResponse(
            total=total,
            page=page,
            size=size,
            items=[KnowledgeFileResponse.model_validate(f) for f in files],
        )


# ── 删除文件 ──

@router.delete("/knowledge-bases/{kb_id}/files/{file_id}", status_code=204)
async def delete_file(
    kb_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """删除文件及关联片段（级联删除）"""
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeFile).where(
                KnowledgeFile.id == file_id,
                KnowledgeFile.knowledge_base_id == kb_id,
            )
        )
        kf = result.scalar_one_or_none()
        if not kf:
            raise HTTPException(status_code=404, detail="文件不存在")
        verify_file_access(kf, current_user)

        file_path = kf.file_path
        await session.delete(kf)
        await session.commit()

        if os.path.exists(file_path):
            os.remove(file_path)


# ── 重试失败文件 ──

@router.post(
    "/knowledge-bases/{kb_id}/files/{file_id}/retry",
    response_model=FileRetryResponse,
)
async def retry_file(
    kb_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
) -> FileRetryResponse:
    """重试失败文件的导入任务"""
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeFile).where(
                KnowledgeFile.id == file_id,
                KnowledgeFile.knowledge_base_id == kb_id,
            )
        )
        kf = result.scalar_one_or_none()
        if not kf:
            raise HTTPException(status_code=404, detail="文件不存在")
        verify_file_access(kf, current_user)

        if kf.status != "failed":
            raise HTTPException(status_code=400, detail="仅可重试失败状态的文件")

        if not os.path.exists(kf.file_path):
            raise HTTPException(
                status_code=400, detail="源文件已被清理，无法重试，请重新上传"
            )

        # 清除残留知识片段
        items_result = await session.execute(
            select(KnowledgeItem).where(KnowledgeItem.file_id == file_id)
        )
        for item in items_result.scalars().all():
            await session.delete(item)

        # 重置状态
        kf.status = "pending"
        kf.error_message = None
        new_task_id = str(uuid.uuid4())

        await session.commit()

    # 重新入队 ARQ
    from app.api.import_api import get_arq

    arq = await get_arq()
    await arq.enqueue_job(
        "process_import",
        task_id=new_task_id,
        file_id=file_id,
        kb_id=kb_id,
        file_path=kf.file_path,
        filename=kf.original_filename,
    )

    return FileRetryResponse(file_id=file_id, task_id=new_task_id, status="pending")


# ── 管理后台：跨知识库文件列表 ──

@router.get("/admin/files", response_model=KnowledgeFileListResponse)
async def admin_list_files(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    status_filter: str | None = Query(None, alias="status"),
    file_type: str | None = Query(None),
    kb_id: str | None = Query(None),
    user_id: str | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: User = Depends(require_super_admin),
) -> KnowledgeFileListResponse:
    """管理后台文件列表（跨知识库/跨用户）"""
    async with async_session() as session:
        base_q = select(KnowledgeFile)
        count_q = select(func.count(KnowledgeFile.id))

        if search:
            filter_clause = KnowledgeFile.original_filename.ilike(f"%{search}%")
            base_q = base_q.where(filter_clause)
            count_q = count_q.where(filter_clause)

        if status_filter:
            base_q = base_q.where(KnowledgeFile.status == status_filter)
            count_q = count_q.where(KnowledgeFile.status == status_filter)

        if file_type:
            base_q = base_q.where(KnowledgeFile.file_type == file_type)
            count_q = count_q.where(KnowledgeFile.file_type == file_type)

        if kb_id:
            base_q = base_q.where(KnowledgeFile.knowledge_base_id == kb_id)
            count_q = count_q.where(KnowledgeFile.knowledge_base_id == kb_id)

        if user_id:
            base_q = base_q.where(KnowledgeFile.user_id == user_id)
            count_q = count_q.where(KnowledgeFile.user_id == user_id)

        total_result = await session.execute(count_q)
        total: int = total_result.scalar() or 0

        sort_col = getattr(KnowledgeFile, sort_by, KnowledgeFile.created_at)
        order = sort_col.desc() if sort_order == "desc" else sort_col.asc()

        offset = (page - 1) * size
        result = await session.execute(
            base_q.order_by(order).offset(offset).limit(size)
        )
        files: Sequence[KnowledgeFile] = result.scalars().all()

        return KnowledgeFileListResponse(
            total=total,
            page=page,
            size=size,
            items=[KnowledgeFileResponse.model_validate(f) for f in files],
        )


# ── 文件类型分类 ──

TEXT_EXTS: set[str] = {".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".xml", ".toml"}
CODE_EXTS: set[str] = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
DOC_EXTS: set[str] = {".pdf", ".docx", ".doc"}
IMAGE_EXTS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

MAX_PREVIEW_CHARS: int = 100 * 1024
MAX_DOC_PREVIEW_CHARS: int = 5000


# ── 预览端点 ──


@router.get("/knowledge-bases/{kb_id}/files/{file_id}/preview")
async def get_file_preview(
    kb_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """获取文件预览内容"""
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeFile).where(
                KnowledgeFile.id == file_id,
                KnowledgeFile.knowledge_base_id == kb_id,
            )
        )
        kf = result.scalar_one_or_none()
        if not kf:
            raise HTTPException(status_code=404, detail="文件不存在")
        verify_file_access(kf, current_user)

        if not os.path.exists(kf.file_path):
            raise HTTPException(status_code=404, detail="源文件已被清理")

        suffix = Path(kf.file_path).suffix.lower()

        if suffix in IMAGE_EXTS:
            return {
                "file_id": kf.id,
                "filename": kf.original_filename,
                "file_type": kf.file_type,
                "content": "",
                "content_type": "image",
                "total_chars": 0,
                "preview_chars": 0,
            }

        if suffix in TEXT_EXTS or suffix in CODE_EXTS:
            raw = Path(kf.file_path).read_text(encoding="utf-8", errors="replace")
            total = len(raw)
            truncated = raw[:MAX_PREVIEW_CHARS]
            content_type = "code" if suffix in CODE_EXTS else "text"
            return {
                "file_id": kf.id,
                "filename": kf.original_filename,
                "file_type": kf.file_type,
                "content": truncated,
                "content_type": content_type,
                "total_chars": total,
                "preview_chars": len(truncated),
            }

        if suffix in DOC_EXTS:
            try:
                from app.services.parser import PARSER_MAP
                parser = PARSER_MAP.get(suffix)
                if parser:
                    text = await parser(kf.file_path)
                else:
                    text = ""
            except Exception as e:
                text = f"[解析失败] {e}"
            total = len(text)
            truncated = text[:MAX_DOC_PREVIEW_CHARS]
            return {
                "file_id": kf.id,
                "filename": kf.original_filename,
                "file_type": kf.file_type,
                "content": truncated,
                "content_type": "text",
                "total_chars": total,
                "preview_chars": len(truncated),
            }

        return {
            "file_id": kf.id,
            "filename": kf.original_filename,
            "file_type": kf.file_type,
            "content": "",
            "content_type": "unsupported",
            "total_chars": 0,
            "preview_chars": 0,
        }


@router.get("/knowledge-bases/{kb_id}/files/{file_id}/raw")
async def get_file_raw(
    kb_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """获取文件原始数据（仅图片）"""
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeFile).where(
                KnowledgeFile.id == file_id,
                KnowledgeFile.knowledge_base_id == kb_id,
            )
        )
        kf = result.scalar_one_or_none()
        if not kf:
            raise HTTPException(status_code=404, detail="文件不存在")
        verify_file_access(kf, current_user)

        suffix = Path(kf.file_path).suffix.lower()
        if suffix not in IMAGE_EXTS:
            raise HTTPException(status_code=400, detail="仅图片文件支持原始数据下载")

        if not os.path.exists(kf.file_path):
            raise HTTPException(status_code=404, detail="源文件已被清理")

        media_type, _ = mimetypes.guess_type(kf.file_path)
        return FileResponse(kf.file_path, media_type=media_type or "application/octet-stream")
