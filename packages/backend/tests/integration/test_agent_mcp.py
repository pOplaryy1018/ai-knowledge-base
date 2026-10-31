import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import anyio
import pytest
from mcp import ClientSession

from app.agent.contracts import ModelTurn, RuntimeContext, ToolRequest
from app.agent.mcp_server import MCPRegistry, create_source_mcp_server
from app.agent.runtime import AgentRuntime
from app.models.knowledge import KnowledgeBase
from app.models.source import Source, SourceDocument, SourceRevision
from app.models.user import User


async def add_source(session, owner, kb, name):
    source = Source(user_id=owner, knowledge_base_id=kb, name=name)
    session.add(source)
    await session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid4().hex, pipeline_version="test", state="ready")
    session.add(revision)
    await session.flush()
    source.current_revision_id = revision.id
    document = SourceDocument(revision_id=revision.id, logical_path="internal/path", text="MCP provides tools.",
                              locator={}, content_hash="synthetic")
    session.add(document)
    await session.flush()
    return source, revision, document


@asynccontextmanager
async def client_for(context, db_session):
    @asynccontextmanager
    async def session_factory():
        yield db_session

    server = create_source_mcp_server(context, session_factory)
    send_to_server, read_by_server = anyio.create_memory_object_stream(0)
    send_to_client, read_by_client = anyio.create_memory_object_stream(0)
    async with anyio.create_task_group() as group:
        group.start_soon(server.run, read_by_server, send_to_client, server.create_initialization_options())
        async with ClientSession(read_by_client, send_to_server) as client:
            await client.initialize()
            yield client
        group.cancel_scope.cancel()


async def test_real_mcp_runtime_reads_source(db_session, owner_kb):
    owner, kb = owner_kb
    source, rev, doc = await add_source(db_session, owner.id, kb.id, "sample")
    context = RuntimeContext(owner_id=owner.id, task_id="task", source_versions={source.id: rev.id})

    async with client_for(context, db_session) as client:
        registry = await MCPRegistry.create(client, context)

        class Provider:
            step = 0

            async def complete(self, messages, tools):
                self.step += 1
                assert len(tools) == 3
                if self.step == 1:
                    return ModelTurn(tool_calls=[ToolRequest(call_id="1", name="list_sources", arguments={})])
                result = json.loads(messages[-1]["content"])
                if self.step == 2:
                    assert result["data"]["items"][0]["source_id"] == source.id
                    return ModelTurn(tool_calls=[ToolRequest(call_id="2", name="list_source_documents",
                                                            arguments={"source_id": source.id})])
                if self.step == 3:
                    assert result["data"]["document_ids"] == [doc.id]
                    return ModelTurn(tool_calls=[ToolRequest(call_id="3", name="read_source_range", arguments={
                        "source_id": source.id, "document_id": doc.id, "offset": 0, "limit": 18,
                    })])
                assert result["data"]["text"] == "MCP provides tools"
                return ModelTurn(text="found source")

        answer = await AgentRuntime(provider=Provider(), registry=registry).run(context, "find source")
        assert (answer.status, answer.answer) == ("completed", "found source")


async def test_mcp_rejects_forged_owner_foreign_source_and_revoked_access(db_session, owner_kb):
    owner, kb = owner_kb
    source, revision, document = await add_source(db_session, owner.id, kb.id, "owned")
    other = User(username=uuid4().hex, hashed_password="test", role="user")
    db_session.add(other)
    await db_session.flush()
    other_kb = KnowledgeBase(name="other", user_id=other.id)
    db_session.add(other_kb)
    await db_session.flush()
    foreign, foreign_revision, foreign_doc = await add_source(db_session, other.id, other_kb.id, "foreign")
    ctx = RuntimeContext(owner_id=owner.id, task_id="task-a", source_versions={source.id: revision.id})
    other_ctx = RuntimeContext(owner_id=other.id, task_id="task-b", source_versions={foreign.id: foreign_revision.id})
    async with client_for(ctx, db_session) as client:
        registry = await MCPRegistry.create(client, ctx)
        with pytest.raises(ValueError):
            await MCPRegistry.create(client, other_ctx)
        result = await client.call_tool("list_sources", {"owner_id": other.id})
        assert result.is_error
        result = await client.call_tool("read_source_range", {
            "source_id": foreign.id, "document_id": foreign_doc.id, "offset": 0, "limit": 4,
        })
        assert result.is_error and "internal/path" not in result.model_dump_json()
        denied = await registry.invoke(other_ctx, ToolRequest(call_id="x", name="list_sources", arguments={}))
        assert not denied.ok
        replacement = SourceRevision(source_id=source.id, raw_hash=uuid4().hex, pipeline_version="test", state="ready")
        db_session.add(replacement)
        await db_session.flush()
        source.current_revision_id = replacement.id
        await db_session.flush()
        old = await registry.invoke(ctx, ToolRequest(call_id="old", name="read_source_range", arguments={
            "source_id": source.id, "document_id": document.id, "offset": 0, "limit": 3,
        }))
        assert old.ok and old.data["revision_id"] == revision.id and old.data["text"] == "MCP"
        source.archived_at = datetime.now(timezone.utc)
        await db_session.flush()
        revoked = await registry.invoke(ctx, ToolRequest(call_id="revoked", name="read_source_range", arguments={
            "source_id": source.id, "document_id": document.id, "offset": 0, "limit": 3,
        }))
        assert not revoked.ok


async def test_mcp_context_must_be_supplied_by_trusted_caller(db_session):
    @asynccontextmanager
    async def factory():
        yield db_session

    with pytest.raises((TypeError, ValueError)):
        create_source_mcp_server(None, factory)
