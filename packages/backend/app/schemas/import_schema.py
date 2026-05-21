"""文档导入相关 Pydantic 请求/响应模型"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ImportTaskResponse(BaseModel):
    """上传成功返回的异步任务标识"""
    file_id: str = Field(..., description="文件记录 ID")
    task_id: str = Field(..., description="异步任务 ID")
    filename: str = Field(..., description="原始文件名")
    status: str = Field(default="pending", description="任务状态")


class ImportProgressEvent(BaseModel):
    """SSE 进度推送事件体"""
    stage: str = Field(..., description="当前阶段: parsing/chunking/vectorizing/storing")
    message: str = Field(default="", description="进度描述")
    percent: int = Field(default=0, ge=0, le=100, description="完成百分比")


class ImportCompleteEvent(BaseModel):
    """SSE 完成事件体"""
    total_chunks: int = Field(..., description="生成的片段总数")
    kb_id: str = Field(..., description="目标知识库 ID")
    preview: list[dict[str, Any]] = Field(default_factory=list, description="片段预览列表")


class FileRetryResponse(BaseModel):
    """重试失败文件响应"""
    file_id: str = Field(..., description="文件记录 ID")
    task_id: str = Field(..., description="新的异步任务 ID")
    status: str = Field(default="pending", description="任务状态")
