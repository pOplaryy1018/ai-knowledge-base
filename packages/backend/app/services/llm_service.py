"""LLM 服务 ── DeepSeek-V3 流式生成"""

import logging
from collections.abc import AsyncGenerator
from typing import Any, cast

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """获取 OpenAI 兼容客户端（懒加载单例）"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


async def stream_generate(
    system_prompt: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """流式调用 LLM，逐 token yield"""
    client = _get_client()
    full_messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]
    try:
        raw = await client.chat.completions.create(
            model=settings.llm_model,
            messages=full_messages,  # type: ignore[arg-type]
            temperature=temperature,
            stream=True,
        )
        stream: AsyncStream[ChatCompletionChunk] = cast(AsyncStream[ChatCompletionChunk], raw)
        async for chunk in stream:
            delta: Any = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
    except Exception:
        logger.exception("LLM 流式调用失败")
        raise


async def generate_system_prompt(
    agent_name: str,
    context_text: str,
    custom_template: str | None = None,
) -> str:
    """构建系统提示词"""
    if custom_template:
        return custom_template.format(context=context_text)

    return (
        f"你是「{agent_name}」，一个基于知识库回答问题的 AI 助手。\n\n"
        f"## 知识库内容\n{context_text}\n\n"
        f"## 回答规则\n"
        f"1. 严格基于上述知识库内容回答问题，不要编造信息。\n"
        f"2. 在引用知识库内容时，使用 [序号] 标注来源（如 [1]、[2]）。\n"
        f"3. 如果知识库中没有相关信息，请明确告知用户「知识库中暂无相关信息」。\n"
        f"4. 回答应清晰、准确、有条理。\n"
    )
