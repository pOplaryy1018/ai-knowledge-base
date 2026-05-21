"""对话路由 ── SSE 流式问答 + 对话历史管理"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, delete
from sse_starlette.sse import EventSourceResponse

from app.core.db import async_session
from app.models.agent import Conversation, Message
from app.models.user import User
from app.core.security import get_current_user
from app.schemas.chat import (
    ChatRequest,
    ConversationResponse,
    ConversationListResponse,
    MessageResponse,
)
from app.services.chat_service import run_chat_stream

router: APIRouter = APIRouter(prefix="/chat", tags=["智能问答"])


@router.post("/agents/{agent_id}/chat")
async def chat_with_agent(
    agent_id: str,
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> EventSourceResponse:
    """SSE 流式问答端点"""

    async def event_generator() -> Any:
        async for sse_event in run_chat_stream(
            agent_id=agent_id,
            user_id=str(user.id),
            message=body.message,
            conversation_id=body.conversation_id,
        ):
            # 检查客户端是否断开
            if await request.is_disconnected():
                break
            yield sse_event

    return EventSourceResponse(event_generator())


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    agent_id: str = Query(..., description="Agent ID"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> ConversationListResponse:
    """获取当前用户在指定 Agent 下的对话列表"""
    async with async_session() as session:
        count_result = await session.execute(
            select(func.count(Conversation.id)).where(
                Conversation.user_id == user.id,
                Conversation.agent_id == agent_id,
            )
        )
        total: int = count_result.scalar() or 0

        result = await session.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user.id,
                Conversation.agent_id == agent_id,
            )
            .order_by(Conversation.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        conversations = result.scalars().all()
        return ConversationListResponse(
            total=total,
            items=[ConversationResponse.model_validate(c) for c in conversations],
        )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    """获取对话的所有历史消息"""
    async with async_session() as session:
        # 验证对话属于当前用户
        conv_result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")

        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        messages = result.scalars().all()
        return [MessageResponse.model_validate(m) for m in messages]


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> None:
    """删除对话"""
    async with async_session() as session:
        conv_result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        await session.delete(conv)
        await session.commit()
