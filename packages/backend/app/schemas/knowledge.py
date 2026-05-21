"""知识库与知识条目 Pydantic 请求/响应模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── 知识库 ──


class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., min_length=1, max_length=255, description="知识库名称")
    description: Optional[str] = Field(None, description="知识库描述")


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""
    id: str
    name: str
    description: Optional[str] = None
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseListResponse(BaseModel):
    """知识库分页响应"""
    total: int
    page: int
    size: int
    items: list[KnowledgeBaseResponse]


# ── 知识条目 ──


class KnowledgeItemResponse(BaseModel):
    """知识条目响应"""
    id: str
    knowledge_base_id: str
    file_id: Optional[str] = None
    title: str
    content: str
    type: str
    status: str
    tags: Optional[list[str]] = None
    source: str
    source_metadata: dict[str, object] = Field(default_factory=dict, description="来源元数据")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeItemListResponse(BaseModel):
    """知识条目分页响应"""
    total: int
    page: int
    size: int
    items: list[KnowledgeItemResponse]


# ── 知识文件 ──


class KnowledgeFileResponse(BaseModel):
    """文件记录响应"""
    id: str
    knowledge_base_id: str
    user_id: str
    filename: str
    original_filename: str
    file_path: str
    file_type: str
    file_size: int
    status: str
    error_message: Optional[str] = None
    chunks_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeFileListResponse(BaseModel):
    """文件列表分页响应"""
    total: int
    page: int
    size: int
    items: list[KnowledgeFileResponse]


class KnowledgeFileUploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str
    task_id: str
    filename: str


class KnowledgeFilePreviewResponse(BaseModel):
    """文件预览响应"""
    filename: str
    content: str
    file_type: str
    total_chars: int
    preview_chars: int
