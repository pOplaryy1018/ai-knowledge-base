"""Register read-only source tools using trusted task context and DB sessions."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.contracts import RuntimeContext
from app.agent.source_reader import list_documents, list_sources, read_document_range
from app.agent.tools import ToolRegistry


class SourceListArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=50)
    after: str | None = None


class DocumentListArgs(SourceListArgs):
    source_id: str


class DocumentRangeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    document_id: str
    offset: int = Field(ge=0, lt=2**31 - 1)
    limit: int = Field(ge=1, le=8000)


def register_source_tools(
    registry: ToolRegistry, session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> None:
    async def sources(context: RuntimeContext, args: SourceListArgs) -> dict[str, Any]:
        async with session_factory() as session:
            return asdict(await list_sources(session, context, limit=args.limit, after=args.after))

    async def documents(context: RuntimeContext, args: DocumentListArgs) -> dict[str, Any]:
        async with session_factory() as session:
            return asdict(await list_documents(session, context, args.source_id, limit=args.limit, after=args.after))

    async def read(context: RuntimeContext, args: DocumentRangeArgs) -> dict[str, Any]:
        async with session_factory() as session:
            return asdict(await read_document_range(session, context, args.source_id, args.document_id,
                                                    offset=args.offset, limit=args.limit))

    registry.register("list_sources", SourceListArgs, sources)
    registry.register("list_source_documents", DocumentListArgs, documents)
    registry.register("read_source_range", DocumentRangeArgs, read)
