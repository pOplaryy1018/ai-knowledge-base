"""Authenticated personal source-scoped chat endpoint."""
from collections.abc import AsyncGenerator
from contextlib import aclosing
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.security import get_current_user
from app.models.user import User
from app.services.scoped_chat_service import prepare_conversation, run_scoped_stream

router = APIRouter(prefix="/chat", tags=["个人问答"])


class ScopedChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    source_ids: list[UUID] = Field(min_length=1, max_length=100)
    conversation_id: UUID | None = None


@router.post("/scoped")
async def scoped_chat(body: ScopedChatRequest, request: Request, user: User = Depends(get_current_user)) -> EventSourceResponse:
    conversation_id, versions, history = await prepare_conversation(body.question, [str(source) for source in body.source_ids],
                                                                  str(user.id), str(body.conversation_id) if body.conversation_id else None)

    async def events() -> AsyncGenerator[bytes, None]:
        async with aclosing(run_scoped_stream(conversation_id, body.question, versions, history, str(user.id))) as stream:
            async for chunk in stream:
                if await request.is_disconnected():
                    break
                yield chunk

    return EventSourceResponse(events())
