"""统计路由 ── 概览、趋势、热门知识、标签词云"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, literal_column, select, text, union_all

from app.core.db import async_session
from app.core.security import get_current_user
from app.models.agent import Agent
from app.models.knowledge import KnowledgeBase, KnowledgeItem
from app.models.user import User
from app.schemas.statistics import (
    OverviewStats,
    RecentActivity,
    ItemsByType,
    TrendPoint,
    TopItem,
    TagFrequency,
)

router: APIRouter = APIRouter(prefix="/statistics", tags=["统计"])


# ── 辅助函数 ──
def today_start() -> datetime:
    """返回今日 00:00 (UTC)"""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def yesterday_start() -> datetime:
    """返回昨日 00:00 (UTC)"""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)


async def _get_accessible_kb_ids(user: User) -> list[str] | None:
    """获取当前用户可访问的知识库 ID 列表，超管返回 None 表示无限制"""
    if user.role == "super_admin":
        return None
    async with async_session() as session:
        result = await session.execute(
            select(KnowledgeBase.id).where(KnowledgeBase.user_id == user.id)
        )
        return [row[0] for row in result.all()]


@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    current_user: User = Depends(get_current_user),
) -> OverviewStats:
    """获取概览统计数据"""
    kb_ids = await _get_accessible_kb_ids(current_user)

    async with async_session() as session:
        # 总条目数
        if kb_ids is not None:
            total_items = await session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.knowledge_base_id.in_(kb_ids)
                )
            )
        else:
            total_items = await session.scalar(
                select(func.count(KnowledgeItem.id))
            )

        # 可用条目数
        if kb_ids is not None:
            available_items = await session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.status == "available",
                    KnowledgeItem.knowledge_base_id.in_(kb_ids),
                )
            )
        else:
            available_items = await session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.status == "available"
                )
            )

        # Agent 总数
        total_agents = await session.scalar(
            select(func.count(Agent.id))
        )

        # 今日问答次数（role='user' 的消息）
        today = today_start()
        if kb_ids is not None:
            today_chats = await session.scalar(
                select(func.count()).select_from(text("messages m JOIN conversations c ON m.conversation_id = c.id")).where(
                    text("m.role = 'user' AND m.created_at >= :today AND c.user_id = :uid")
                ).params(today=today, uid=current_user.id)
            )
        else:
            today_chats = await session.scalar(
                select(func.count()).select_from(text("messages")).where(
                    text("role = 'user' AND created_at >= :today")
                ).params(today=today)
            )

        # 今日新增条目
        if kb_ids is not None:
            items_today = await session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.created_at >= today,
                    KnowledgeItem.knowledge_base_id.in_(kb_ids),
                )
            )
        else:
            items_today = await session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.created_at >= today
                )
            )

        # 昨日新增条目（用于环比）
        yesterday = yesterday_start()
        if kb_ids is not None:
            items_yesterday = await session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.created_at >= yesterday,
                    KnowledgeItem.created_at < today,
                    KnowledgeItem.knowledge_base_id.in_(kb_ids),
                )
            )
        else:
            items_yesterday = await session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.created_at >= yesterday,
                    KnowledgeItem.created_at < today,
                )
            )

        # 昨日问答次数
        if kb_ids is not None:
            chats_yesterday = await session.scalar(
                select(func.count()).select_from(text("messages m JOIN conversations c ON m.conversation_id = c.id")).where(
                    text("m.role = 'user' AND m.created_at >= :yesterday AND m.created_at < :today AND c.user_id = :uid")
                ).params(yesterday=yesterday, today=today, uid=current_user.id)
            )
        else:
            chats_yesterday = await session.scalar(
                select(func.count()).select_from(text("messages")).where(
                    text("role = 'user' AND created_at >= :yesterday AND created_at < :today")
                ).params(yesterday=yesterday, today=today)
            )

        # 计算环比
        items_growth = 0.0
        if items_yesterday and items_yesterday > 0:
            items_growth = round((items_today - items_yesterday) / items_yesterday * 100, 1)

        chats_growth = 0.0
        if chats_yesterday and chats_yesterday > 0:
            chats_growth = round((today_chats - chats_yesterday) / chats_yesterday * 100, 1)

        return OverviewStats(
            total_items=total_items or 0,
            available_items=available_items or 0,
            total_agents=total_agents or 0,
            today_chats=today_chats or 0,
            items_growth=items_growth,
            chats_growth=chats_growth,
        )


@router.get("/recent-activities", response_model=list[RecentActivity])
async def get_recent_activities(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
) -> list[RecentActivity]:
    """获取最近动态（合并知识库/条目/Agent 的创建记录）"""
    kb_ids = await _get_accessible_kb_ids(current_user)

    async with async_session() as session:
        # 知识库创建
        kb_stmt = (
            select(
                KnowledgeBase.id.label("id"),
                literal_column("'kb_created'").label("type"),
                func.concat("创建知识库「", KnowledgeBase.name, "」").label("title"),
                KnowledgeBase.created_at.label("created_at"),
            )
        )
        if kb_ids is not None:
            kb_stmt = kb_stmt.where(KnowledgeBase.user_id == current_user.id)
        kb_stmt = kb_stmt.order_by(KnowledgeBase.created_at.desc()).limit(limit)

        # 条目创建
        item_stmt = (
            select(
                KnowledgeItem.id.label("id"),
                literal_column("'item_created'").label("type"),
                func.concat("新增知识条目「", KnowledgeItem.title, "」").label("title"),
                KnowledgeItem.created_at.label("created_at"),
            )
        )
        if kb_ids is not None:
            item_stmt = item_stmt.where(KnowledgeItem.knowledge_base_id.in_(kb_ids))
        item_stmt = item_stmt.order_by(KnowledgeItem.created_at.desc()).limit(limit)

        # 条目导入
        import_stmt = (
            select(
                KnowledgeItem.id.label("id"),
                literal_column("'import_done'").label("type"),
                func.concat("导入知识条目「", KnowledgeItem.title, "」").label("title"),
                KnowledgeItem.created_at.label("created_at"),
            ).where(KnowledgeItem.source == "import")
        )
        if kb_ids is not None:
            import_stmt = import_stmt.where(KnowledgeItem.knowledge_base_id.in_(kb_ids))
        import_stmt = import_stmt.order_by(KnowledgeItem.created_at.desc()).limit(limit)

        # Agent 创建
        agent_stmt = (
            select(
                Agent.id.label("id"),
                literal_column("'agent_created'").label("type"),
                func.concat("创建 Agent「", Agent.name, "」").label("title"),
                Agent.created_at.label("created_at"),
            ).order_by(Agent.created_at.desc()).limit(limit)
        )

        combined = union_all(kb_stmt, item_stmt, import_stmt, agent_stmt)
        sub = combined.subquery()
        stmt = (
            select(
                sub.c.id,
                sub.c.type,
                sub.c.title,
                sub.c.created_at,
            )
            .order_by(sub.c.created_at.desc())
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        return [
            RecentActivity(
                id=row.id,
                type=row.type,
                title=row.title,
                created_at=row.created_at,
            )
            for row in rows
        ]


@router.get("/items-by-type", response_model=list[ItemsByType])
async def get_items_by_type(
    kb_id: str | None = Query(None, description="知识库 ID 筛选"),
    current_user: User = Depends(get_current_user),
) -> list[ItemsByType]:
    """按类型统计知识条目分布"""
    kb_ids = await _get_accessible_kb_ids(current_user)

    async with async_session() as session:
        conditions = []
        if kb_id:
            conditions.append(KnowledgeItem.knowledge_base_id == kb_id)
        if kb_ids is not None:
            conditions.append(KnowledgeItem.knowledge_base_id.in_(kb_ids))

        stmt = (
            select(
                KnowledgeItem.type.label("type"),
                func.count(KnowledgeItem.id).label("count"),
            )
            .where(*conditions)
            .group_by(KnowledgeItem.type)
            .order_by(text("count DESC"))
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        return [ItemsByType(type=row.type, count=row.count) for row in rows]


@router.get("/items-trend", response_model=list[TrendPoint])
async def get_items_trend(
    days: int = Query(30, ge=1, le=365),
    kb_id: str | None = Query(None, description="知识库 ID 筛选"),
    current_user: User = Depends(get_current_user),
) -> list[TrendPoint]:
    """获取知识条目增长趋势"""
    kb_ids = await _get_accessible_kb_ids(current_user)

    async with async_session() as session:
        conditions = [
            KnowledgeItem.created_at >= func.now() - text(f"'{days} days'::interval"),
        ]
        if kb_id:
            conditions.append(KnowledgeItem.knowledge_base_id == kb_id)
        if kb_ids is not None:
            conditions.append(KnowledgeItem.knowledge_base_id.in_(kb_ids))

        stmt = (
            select(
                func.to_char(KnowledgeItem.created_at, "YYYY-MM-DD").label("date"),
                func.count(KnowledgeItem.id).label("count"),
            )
            .where(*conditions)
            .group_by(text("date"))
            .order_by(text("date ASC"))
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        return [TrendPoint(date=row.date, count=row.count) for row in rows]


@router.get("/chat-trend", response_model=list[TrendPoint])
async def get_chat_trend(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
) -> list[TrendPoint]:
    """获取问答活跃趋势"""
    kb_ids = await _get_accessible_kb_ids(current_user)

    async with async_session() as session:
        if kb_ids is not None:
            stmt = (
                select(
                    func.to_char(text("m.created_at"), "YYYY-MM-DD").label("date"),
                    func.count().label("count"),
                )
                .select_from(text("messages m JOIN conversations c ON m.conversation_id = c.id"))
                .where(
                    text("m.role = 'user'"),
                    text(f"m.created_at >= NOW() - '{days} days'::interval"),
                    text("c.user_id = :uid"),
                )
                .params(uid=current_user.id)
                .group_by(text("date"))
                .order_by(text("date ASC"))
            )
        else:
            stmt = (
                select(
                    func.to_char(text("created_at"), "YYYY-MM-DD").label("date"),
                    func.count().label("count"),
                )
                .select_from(text("messages"))
                .where(
                    text("role = 'user'"),
                    text(f"created_at >= NOW() - '{days} days'::interval"),
                )
                .group_by(text("date"))
                .order_by(text("date ASC"))
            )

        result = await session.execute(stmt)
        rows = result.fetchall()

        return [TrendPoint(date=row.date, count=row.count) for row in rows]


@router.get("/top-items", response_model=list[TopItem])
async def get_top_items(
    limit: int = Query(20, ge=1, le=100),
    kb_id: str | None = Query(None, description="知识库 ID 筛选"),
    current_user: User = Depends(get_current_user),
) -> list[TopItem]:
    """获取被引用最多的知识条目"""
    kb_ids = await _get_accessible_kb_ids(current_user)

    async with async_session() as session:
        # 从 messages.citations JSONB 中统计 knowledge_title 出现频率
        if kb_ids is not None:
            stmt = (
                select(
                    literal_column("citation->>'knowledge_title'").label("title"),
                    func.count().label("count"),
                )
                .select_from(
                    text("messages m JOIN conversations c ON m.conversation_id = c.id, jsonb_array_elements(m.citations) AS citation"),
                )
                .where(
                    text("m.citations IS NOT NULL"),
                    text("c.user_id = :uid"),
                )
                .params(uid=current_user.id)
                .group_by(text("title"))
                .order_by(text("count DESC"))
                .limit(limit)
            )
        else:
            stmt = (
                select(
                    literal_column("citation->>'knowledge_title'").label("title"),
                    func.count().label("count"),
                )
                .select_from(
                    text("messages, jsonb_array_elements(messages.citations) AS citation"),
                )
                .where(text("messages.citations IS NOT NULL"))
                .group_by(text("title"))
                .order_by(text("count DESC"))
                .limit(limit)
            )

        result = await session.execute(stmt)
        rows = result.fetchall()

        return [
            TopItem(title=row.title or "未知", count=row.count)
            for row in rows
        ]


@router.get("/tags-wordcloud", response_model=list[TagFrequency])
async def get_tags_wordcloud(
    kb_id: str | None = Query(None, description="知识库 ID 筛选"),
    current_user: User = Depends(get_current_user),
) -> list[TagFrequency]:
    """获取标签词云数据"""
    kb_ids = await _get_accessible_kb_ids(current_user)

    async with async_session() as session:
        conditions = ["tags IS NOT NULL"]
        params: dict = {}

        if kb_id:
            conditions.append("knowledge_base_id = :kb_id")
            params["kb_id"] = kb_id
        if kb_ids is not None:
            if not kb_ids:
                conditions.append("FALSE")
            else:
                conditions.append("knowledge_base_id = ANY(:kb_ids)")
                params["kb_ids"] = kb_ids

        where_clause = " AND ".join(conditions)

        stmt = (
            select(
                literal_column("unnest(tags)").label("tag"),
                func.count().label("count"),
            )
            .select_from(text("knowledge_items"))
            .where(text(where_clause))
            .group_by(text("tag"))
            .order_by(text("count DESC"))
        )

        result = await session.execute(stmt, params)
        rows = result.fetchall()

        return [TagFrequency(tag=row.tag, count=row.count) for row in rows]
