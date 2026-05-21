"""问答模块 Pydantic 请求/响应模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Agent ──


class AgentCreate(BaseModel):
    """创建 Agent 请求"""
    name: str = Field(..., min_length=1, max_length=255, description="Agent 名称")
    description: Optional[str] = Field(None, description="Agent 描述")
    knowledge_ids: list[str] = Field(default_factory=list, description="关联的知识条目 ID 列表")
    prompt_template: Optional[str] = Field(None, description="自定义系统提示词模板")


class AgentUpdate(BaseModel):
    """更新 Agent 请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    knowledge_ids: Optional[list[str]] = None
    prompt_template: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent 响应"""
    id: str
    name: str
    description: Optional[str] = None
    knowledge_ids: list[str]
    prompt_template: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentListResponse(BaseModel):
    """Agent 列表响应"""
    total: int
    items: list[AgentResponse]


# ── 对话 ──


class ConversationResponse(BaseModel):
    """对话响应"""
    id: str
    agent_id: str
    user_id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    total: int
    items: list[ConversationResponse]


# ── 消息 ──


class CitationItem(BaseModel):
    """单条引用来源"""
    index: int = Field(..., description="引用序号")
    content: str = Field(..., description="引用片段文本")
    knowledge_title: str = Field(..., description="来源文档标题")
    score: float = Field(..., description="相似度分数")


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    conversation_id: str
    role: str
    content: str
    citations: Optional[list[dict[str, object]]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 对话请求 ──


class ChatRequest(BaseModel):
    """发起对话请求"""
    message: str = Field(..., min_length=1, description="用户问题")
    conversation_id: Optional[str] = Field(None, description="对话 ID，不传则创建新会话")
