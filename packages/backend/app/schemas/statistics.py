"""统计数据 Pydantic 响应模型"""

from datetime import datetime

from pydantic import BaseModel, Field


class OverviewStats(BaseModel):
    """概览统计数据"""
    total_items: int = Field(..., description="知识条目总数")
    available_items: int = Field(..., description="可用条目数")
    total_agents: int = Field(..., description="Agent 总数")
    today_chats: int = Field(..., description="今日问答次数")
    items_growth: float = Field(0.0, description="条目环比增长率")
    chats_growth: float = Field(0.0, description="问答环比增长率")


class RecentActivity(BaseModel):
    """最近动态"""
    id: str
    type: str = Field(..., description="kb_created / item_created / import_done / agent_created")
    title: str
    created_at: datetime


class ItemsByType(BaseModel):
    """按类型统计"""
    type: str
    count: int


class TrendPoint(BaseModel):
    """趋势数据点"""
    date: str
    count: int


class TopItem(BaseModel):
    """热门知识条目"""
    title: str
    count: int = Field(..., description="被引用次数")


class TagFrequency(BaseModel):
    """标签频率"""
    tag: str
    count: int
