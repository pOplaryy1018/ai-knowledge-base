import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from app.agent.contracts import ModelTurn, RuntimeContext, ToolRequest
from app.agent.runtime import AgentRuntime
from app.agent.source_reader import capture_source_versions
from app.agent.source_tools import register_source_tools
from app.agent.tools import ToolRegistry
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
    doc = SourceDocument(revision_id=revision.id, logical_path="private/path", text="RAG uses retrieval evidence.",
                         locator={}, content_hash="synthetic")
    session.add(doc)
    await session.flush()
    return source, revision, doc


def registry_for(session):
    @asynccontextmanager
    async def factory():
        yield session
    registry = ToolRegistry()
    register_source_tools(registry, factory)
    return registry


async def test_runtime_discovers_and_reads_source_with_real_registry(db_session, owner_kb):
    owner, kb = owner_kb
    source, rev, doc = await add_source(db_session, owner.id, kb.id, "sample")
    context = RuntimeContext(owner_id=owner.id, task_id="task", source_versions={source.id: rev.id})
    registry = registry_for(db_session)

    class Provider:
        count = 0

        async def complete(self, messages, tools):
            self.count += 1
            assert {item["function"]["name"] for item in tools} == {
                "list_sources", "list_source_documents", "read_source_range",
            }
            if self.count == 1:
                return ModelTurn(tool_calls=[ToolRequest(call_id="c1", name="list_sources", arguments={})])
            result = json.loads(messages[-1]["content"])
            if self.count == 2:
                assert result["data"]["items"][0]["source_id"] == source.id
                assert "RAG uses" not in messages[-1]["content"]
                return ModelTurn(tool_calls=[ToolRequest(
                    call_id="c2", name="list_source_documents", arguments={"source_id": source.id},
                )])
            if self.count == 3:
                assert result["data"]["document_ids"] == [doc.id]
                return ModelTurn(tool_calls=[ToolRequest(call_id="c3", name="read_source_range", arguments={
                    "source_id": source.id, "document_id": doc.id, "offset": 0, "limit": 28,
                })])
            assert result["data"]["text"] == doc.text
            assert result["data"]["revision_id"] == rev.id
            return ModelTurn(text="found source")

    result = await AgentRuntime(provider=Provider(), registry=registry).run(context, "find evidence")
    assert (result.status, result.answer) == ("completed", "found source")


async def test_source_tools_enforce_owner_snapshot_and_revocation(db_session, owner_kb):
    owner, kb = owner_kb
    source, rev, doc = await add_source(db_session, owner.id, kb.id, "owned")
    other = User(username=uuid4().hex, hashed_password="test", role="user")
    db_session.add(other)
    await db_session.flush()
    other_kb = KnowledgeBase(user_id=other.id, name="foreign")
    db_session.add(other_kb)
    await db_session.flush()
    foreign, _, foreign_doc = await add_source(db_session, other.id, other_kb.id, "private foreign")
    ctx = RuntimeContext(owner_id=owner.id, task_id="task", source_versions=await capture_source_versions(db_session, owner.id))
    registry = registry_for(db_session)

    async def call(name, args):
        return await registry.invoke(ctx, ToolRequest(call_id=uuid4().hex, name=name, arguments=args))

    forged = await call("list_sources", {"owner_id": other.id})
    assert not forged.ok and forged.error == "invalid_arguments"
    sources = await call("list_sources", {})
    assert sources.ok and len(sources.data["items"]) == 1
    assert "private foreign" not in repr(sources.data)
    assert "private/path" not in repr(sources.data)
    assert not (await call("list_source_documents", {"source_id": foreign.id})).ok
    assert not (await call("read_source_range", {
        "source_id": source.id, "document_id": foreign_doc.id, "offset": 0, "limit": 10,
    })).ok
    assert not (await call("read_source_range", {
        "source_id": source.id, "document_id": doc.id, "offset": 0, "limit": 8001,
    })).ok
    replacement = SourceRevision(source_id=source.id, raw_hash=uuid4().hex, pipeline_version="test", state="ready")
    db_session.add(replacement)
    await db_session.flush()
    source.current_revision_id = replacement.id
    await db_session.flush()
    old = await call("read_source_range", {"source_id": source.id, "document_id": doc.id, "offset": 0, "limit": 5})
    assert old.ok and old.data["revision_id"] == rev.id and old.data["text"] == "RAG u"
    source.archived_at = datetime.now(timezone.utc)
    await db_session.flush()
    assert not (await call("read_source_range", {
        "source_id": source.id, "document_id": doc.id, "offset": 0, "limit": 5,
    })).ok
    assert (await call("list_sources", {})).data["items"] == []


async def test_source_tool_paginates_past_100_and_rejects_foreign_cursor(db_session, owner_kb):
    owner, kb = owner_kb
    for i in range(103):
        await add_source(db_session, owner.id, kb.id, f"sample-{i}")
    ctx = RuntimeContext(owner_id=owner.id, task_id="task", source_versions=await capture_source_versions(db_session, owner.id))
    registry = registry_for(db_session)
    seen = []
    cursor = None
    while True:
        result = await registry.invoke(ctx, ToolRequest(call_id=uuid4().hex, name="list_sources", arguments={"after": cursor}))
        assert result.ok
        seen.extend(item["source_id"] for item in result.data["items"])
        cursor = result.data["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 103
    invalid = await registry.invoke(ctx, ToolRequest(call_id="bad", name="list_sources", arguments={"after": str(uuid4())}))
    assert not invalid.ok
