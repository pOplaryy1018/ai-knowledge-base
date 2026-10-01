"""对话服务 ── 检索 + 生成 + 消息持久化"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.db import async_session
from app.models.agent import Agent, Conversation, Message
from app.services.llm_service import generate_system_prompt, stream_generate
from app.services.search_service import hybrid_search

logger = logging.getLogger(__name__)


# ── 消息存储 ──


async def save_message(
    conversation_id: str,
    role: str,
    content: str,
    citations: list[dict[str, object]] | None = None,
) -> Message:
    """保存一条消息到数据库"""
    async with async_session() as session:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=citations or None,
        )
        session.add(msg)
        # 更新对话的 updated_at
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
        return msg


async def get_or_create_conversation(
    agent_id: str,
    user_id: str,
    conversation_id: str | None = None,
    title: str | None = None,
) -> Conversation:
    """获取或创建对话"""
    async with async_session() as session:
        if conversation_id:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.agent_id == agent_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                return conv
            raise ValueError("对话不存在或不属于当前 Agent")

        conv = Conversation(
            agent_id=agent_id,
            user_id=user_id,
            title=title,
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv


async def get_conversation_history(conversation_id: str) -> list[dict[str, str]]:
    """获取对话历史消息列表（用于组装 LLM context）"""
    async with async_session() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(20)
        )
        messages = list(reversed(result.scalars().all()))
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]


# ── 核心对话流程 ──


async def run_chat_stream(
    agent_id: str,
    user_id: str,
    message: str,
    conversation_id: str | None = None,
    is_admin: bool = False,
) -> AsyncGenerator[bytes, None]:
    """执行一次对话并流式返回 SSE 事件（产出 bytes 避免 sse-starlette 二次包装）"""
    # 1. 获取 Agent 信息
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            error_data = json.dumps({"message": "Agent 不存在"}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n".encode("utf-8")
            return

        if not agent.knowledge_ids:
            error_data = json.dumps({"message": "该 Agent 未关联任何知识条目"}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n".encode("utf-8")
            return

    # 2. 创建或获取对话
    try:
        conv = await get_or_create_conversation(agent_id=agent_id, user_id=user_id, conversation_id=conversation_id, title=message[:100])
    except ValueError as error:
        yield f"event: error\ndata: {json.dumps({'message': str(error)}, ensure_ascii=False)}\n\n".encode()
        return
    conversation_id = conv.id

    # 发送 conversation_id
    conv_data = json.dumps({"conversation_id": conversation_id}, ensure_ascii=False)
    yield f"event: meta\ndata: {conv_data}\n\n".encode("utf-8")

    citations: list[dict[str, object]] = []
    try:
        await save_message(conversation_id, "user", message)
        search_results = await hybrid_search(
            knowledge_ids=list(agent.knowledge_ids),
            query=message,
            top_k=5,
            user_id=user_id,
            is_admin=is_admin,
        )
        context_parts: list[str] = []
        for i, sr in enumerate(search_results, start=1):
            citations.append({
                "index": i,
                "content": sr.item.content[:500],
                "knowledge_title": sr.item.title,
                "score": round(sr.score, 4),
            })
            context_parts.append(f"[{i}] 标题: {sr.item.title}\n内容: {sr.item.content}\n")
        context_text = "\n".join(context_parts) if context_parts else "暂无相关知识条目。"
        system_prompt = await generate_system_prompt(
            agent_name=agent.name,
            context_text=context_text,
            custom_template=agent.prompt_template,
        )
        history = await get_conversation_history(conversation_id)
        recent_history = history[-20:]
    except Exception:
        logger.exception("对话上下文准备失败")
        error_data = json.dumps({"message": "暂时无法准备回答，请稍后重试。"}, ensure_ascii=False)
        yield f"event: error\ndata: {error_data}\n\n".encode("utf-8")
        return

    # 7. 流式生成回答
    full_answer: list[str] = []
    generation_failed = False
    persistence_failed = False
    try:
        async for token in stream_generate(system_prompt, recent_history):
            full_answer.append(token)
            token_data = json.dumps({"content": token}, ensure_ascii=False)
            yield f"event: token\ndata: {token_data}\n\n".encode("utf-8")
    except Exception:
        logger.exception("LLM 调用失败")
        generation_failed = True
    finally:
        # One persistence path covers success, provider failure, task cancellation
        # and generator close. Shield the commit from client cancellation.
        if full_answer:
            try:
                await asyncio.shield(save_message(conversation_id, "assistant", "".join(full_answer), citations))
            except Exception:
                logger.exception("回答保存失败")
                persistence_failed = True

    if generation_failed or persistence_failed:
        error_data = json.dumps({"message": "回答生成或保存中断，请稍后重试。"}, ensure_ascii=False)
        yield f"event: error\ndata: {error_data}\n\n".encode("utf-8")
        return

    # 9. 发送引用列表
    citations_data = json.dumps(citations, ensure_ascii=False)
    yield f"event: citations\ndata: {citations_data}\n\n".encode("utf-8")

    # 10. 完成
    done_data = json.dumps({"conversation_id": conversation_id}, ensure_ascii=False)
    yield f"event: done\ndata: {done_data}\n\n".encode("utf-8")
