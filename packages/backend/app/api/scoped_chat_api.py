"""Authenticated personal source-scoped chat endpoint."""
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Literal, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sse_starlette.sse import EventSourceResponse

from app.core.security import get_current_user
from app.models.user import User
from app.services.scoped_chat_service import (
    prepare_conversation,
    run_comparison_stream,
    run_scoped_stream,
)

router = APIRouter(prefix="/chat", tags=["个人问答"])


class ScopedChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    source_ids: list[UUID] = Field(min_length=1, max_length=100)
    conversation_id: UUID | None = None
    response_mode: Literal["text", "comparison"] = "text"

    @model_validator(mode="after")
    def validate_comparison_scope(self) -> Self:
        if self.response_mode == "comparison" and (
            not 2 <= len(self.source_ids) <= 4 or len(set(self.source_ids)) != len(self.source_ids)
        ):
            raise ValueError("资料对比需要选择2至4份不同资料")
        return self


@router.post("/scoped")
async def scoped_chat(body: ScopedChatRequest, request: Request, user: User = Depends(get_current_user)) -> EventSourceResponse:
    conversation_id, versions, history = await prepare_conversation(body.question, [str(source) for source in body.source_ids],
                                                                  str(user.id), str(body.conversation_id) if body.conversation_id else None)

    async def events() -> AsyncGenerator[bytes, None]:
        selected_stream = (
            run_comparison_stream(conversation_id, body.question, versions, str(user.id))
            if body.response_mode == "comparison"
            else run_scoped_stream(conversation_id, body.question, versions, history, str(user.id))
        )
        async with aclosing(selected_stream) as stream:
            async for chunk in stream:
                if await request.is_disconnected():
                    break
                yield chunk

    return EventSourceResponse(events())
