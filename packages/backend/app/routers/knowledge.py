"""知识库与知识条目路由 ── CRUD + 分页 + 搜索"""

from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.db import async_session
from app.core.security import get_current_user
from app.models.knowledge import KnowledgeBase, KnowledgeItem
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    KnowledgeItemListResponse,
    KnowledgeItemResponse,
)

router: APIRouter = APIRouter(tags=["知识库管理"])

def verify_kb_access(kb: KnowledgeBase, user: User) -> None:
    """校验当前用户是否有权访问该知识库（owner 或 super_admin）"""
    if user.role != "super_admin" and kb.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该知识库")


# ═══════════════════════════════════════════
# 知识库 CRUD
# ═══════════════════════════════════════════


@router.post("/knowledge-bases", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseResponse:
    """创建知识库"""
    async with async_session() as session:
        kb: KnowledgeBase = KnowledgeBase(
            name=body.name,
            description=body.description,
            user_id=current_user.id,
        )
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        return KnowledgeBaseResponse.model_validate(kb)


@router.get("/knowledge-bases", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="按名称模糊搜索"),
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseListResponse:
    """获取知识库列表（分页），普通用户仅看自己的，超管看全部"""
    async with async_session() as session:
        base_q = select(KnowledgeBase)
        count_q = select(func.count(KnowledgeBase.id))

        # 数据隔离：普通用户只看自己的
        if current_user.role != "super_admin":
            base_q = base_q.where(KnowledgeBase.user_id == current_user.id)
            count_q = count_q.where(KnowledgeBase.user_id == current_user.id)

        if search:
            filter_clause = KnowledgeBase.name.ilike(f"%{search}%")
            base_q = base_q.where(filter_clause)
            count_q = count_q.where(filter_clause)

        total_result = await session.execute(count_q)
        total: int = total_result.scalar() or 0

        offset: int = (page - 1) * size
        result = await session.execute(
            base_q.order_by(KnowledgeBase.created_at.desc()).offset(offset).limit(size)
        )
        kbs: Sequence[KnowledgeBase] = result.scalars().all()

        return KnowledgeBaseListResponse(
            total=total,
            page=page,
            size=size,
            items=[KnowledgeBaseResponse.model_validate(kb) for kb in kbs],
        )


@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseResponse:
    """获取单个知识库详情"""
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb: KnowledgeBase | None = result.scalar_one_or_none()
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        verify_kb_access(kb, current_user)
        return KnowledgeBaseResponse.model_validate(kb)


@router.put("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    body: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseResponse:
    """更新知识库"""
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb: KnowledgeBase | None = result.scalar_one_or_none()
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        verify_kb_access(kb, current_user)

        update_data: dict[str, object] = body.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(kb, key, value)

        await session.commit()
        await session.refresh(kb)
        return KnowledgeBaseResponse.model_validate(kb)


@router.delete("/knowledge-bases/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """删除知识库（级联删除所有知识条目）"""
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb: KnowledgeBase | None = result.scalar_one_or_none()
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        verify_kb_access(kb, current_user)

        await session.delete(kb)
        await session.commit()


# ═══════════════════════════════════════════
# 知识条目（只读）
# ═══════════════════════════════════════════


@router.get(
    "/knowledge-bases/{kb_id}/items",
    response_model=KnowledgeItemListResponse,
)
async def list_knowledge_items(
    kb_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="按标题或内容模糊搜索"),
    status_filter: str | None = Query(None, alias="status", description="按状态筛选"),
    tag: str | None = Query(None, description="按标签筛选"),
    current_user: User = Depends(get_current_user),
) -> KnowledgeItemListResponse:
    """获取知识条目列表（分页+搜索+筛选）"""
    async with async_session() as session:
        # 验证知识库存在
        kb_result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb: KnowledgeBase | None = kb_result.scalar_one_or_none()
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        verify_kb_access(kb, current_user)

        base_q = select(KnowledgeItem).where(KnowledgeItem.knowledge_base_id == kb_id)
        count_q = select(func.count(KnowledgeItem.id)).where(
            KnowledgeItem.knowledge_base_id == kb_id
        )

        # 搜索
        if search:
            search_filter = KnowledgeItem.title.ilike(
                f"%{search}%"
            ) | KnowledgeItem.content.ilike(f"%{search}%")
            base_q = base_q.where(search_filter)
            count_q = count_q.where(search_filter)

        # 状态筛选
        if status_filter:
            base_q = base_q.where(KnowledgeItem.status == status_filter)
            count_q = count_q.where(KnowledgeItem.status == status_filter)

        # 标签筛选（pg 数组包含查询）
        if tag:
            base_q = base_q.where(KnowledgeItem.tags.any(tag))  # type: ignore[arg-type]
            count_q = count_q.where(KnowledgeItem.tags.any(tag))  # type: ignore[arg-type]

        total_result = await session.execute(count_q)
        total: int = total_result.scalar() or 0

        offset_val: int = (page - 1) * size
        result = await session.execute(
            base_q.order_by(KnowledgeItem.created_at.desc())
            .offset(offset_val)
            .limit(size)
        )
        items_list: Sequence[KnowledgeItem] = result.scalars().all()

        return KnowledgeItemListResponse(
            total=total,
            page=page,
            size=size,
            items=[KnowledgeItemResponse.model_validate(item) for item in items_list],
        )
