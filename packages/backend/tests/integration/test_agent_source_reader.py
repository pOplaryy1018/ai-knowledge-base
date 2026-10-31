from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.agent.contracts import RuntimeContext
from app.agent.source_reader import capture_source_versions, list_documents, read_document_range
from app.models.knowledge import KnowledgeBase
from app.models.source import Source, SourceDocument, SourceRevision
from app.models.user import User


async def make_source(session, owner_id, kb_id, label):
    source = Source(user_id=owner_id, knowledge_base_id=kb_id, name=label)
    session.add(source)
    await session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid4().hex, pipeline_version="test", state="ready")
    session.add(revision)
    await session.flush()
    source.current_revision_id = revision.id
    doc = SourceDocument(revision_id=revision.id, logical_path="internal/path", text="abcdefghij",
                         locator={}, content_hash="synthetic")
    session.add(doc)
    await session.flush()
    return source, revision, doc


async def test_snapshot_covers_all_owned_ready_sources(db_session, owner_kb):
    owner, kb = owner_kb
    other = User(username=uuid4().hex, hashed_password="test", role="user")
    db_session.add(other)
    await db_session.flush()
    second_kb = KnowledgeBase(name="second", user_id=owner.id)
    other_kb = KnowledgeBase(name="foreign", user_id=other.id)
    db_session.add_all([second_kb, other_kb])
    await db_session.flush()
    first, first_rev, _ = await make_source(db_session, owner.id, kb.id, "a")
    second, second_rev, _ = await make_source(db_session, owner.id, second_kb.id, "b")
    foreign, _, _ = await make_source(db_session, other.id, other_kb.id, "foreign")
    archived, _, _ = await make_source(db_session, owner.id, kb.id, "archived")
    archived.archived_at = datetime.now(timezone.utc)
    pending = Source(user_id=owner.id, knowledge_base_id=kb.id, name="pending")
    db_session.add(pending)
    await db_session.flush()
    for index in range(101):
        await make_source(db_session, owner.id, kb.id, f"synthetic-{index}")
    versions = await capture_source_versions(db_session, owner.id)
    assert len(versions) == 103
    assert versions[first.id] == first_rev.id
    assert versions[second.id] == second_rev.id
    assert foreign.id not in versions and archived.id not in versions and pending.id not in versions


async def test_read_pins_revision_and_rechecks_access(db_session, owner_kb):
    owner, kb = owner_kb
    source, old, doc = await make_source(db_session, owner.id, kb.id, "sample")
    ctx = RuntimeContext(owner_id=owner.id, task_id="task", source_versions={source.id: old.id})
    replacement = SourceRevision(source_id=source.id, raw_hash=uuid4().hex, pipeline_version="test", state="ready")
    db_session.add(replacement)
    await db_session.flush()
    source.current_revision_id = replacement.id
    await db_session.flush()
    result = await read_document_range(db_session, ctx, source.id, doc.id, offset=2, limit=4)
    assert result.text == "cdef"
    assert (result.revision_id, result.char_start, result.char_end) == (old.id, 2, 6)
    assert "internal/path" not in repr(result)
    foreign = RuntimeContext(owner_id=str(uuid4()), task_id="task", source_versions={source.id: old.id})
    with pytest.raises(LookupError):
        await read_document_range(db_session, foreign, source.id, doc.id, offset=0, limit=3)
    with pytest.raises(LookupError):
        await read_document_range(db_session, ctx, source.id, str(uuid4()), offset=0, limit=3)
    source.archived_at = datetime.now(timezone.utc)
    await db_session.flush()
    with pytest.raises(LookupError):
        await read_document_range(db_session, ctx, source.id, doc.id, offset=0, limit=3)


async def test_document_pagination_and_invalid_ranges(db_session, owner_kb):
    owner, kb = owner_kb
    source, rev, doc = await make_source(db_session, owner.id, kb.id, "sample")
    for i in range(3):
        db_session.add(SourceDocument(revision_id=rev.id, logical_path=f"internal/{i}", text="x",
                                      locator={}, content_hash="synthetic"))
    await db_session.flush()
    ctx = RuntimeContext(owner_id=owner.id, task_id="task", source_versions={source.id: rev.id})
    first = await list_documents(db_session, ctx, source.id, limit=2)
    second = await list_documents(db_session, ctx, source.id, limit=2, after=first.next_cursor)
    assert len(first.document_ids) == len(second.document_ids) == 2
    assert len(set(first.document_ids + second.document_ids)) == 4
    assert second.next_cursor is None
    for offset, limit in [(-1, 1), (0, 8001), (True, 1), (0, 0), (11, 1), (2**31, 1)]:
        with pytest.raises(ValueError):
            await read_document_range(db_session, ctx, source.id, doc.id, offset=offset, limit=limit)
    source.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()
    with pytest.raises(LookupError):
        await list_documents(db_session, ctx, source.id)


async def test_knowledge_base_ownership_change_revokes_read(db_session, owner_kb):
    owner, kb = owner_kb
    source, rev, doc = await make_source(db_session, owner.id, kb.id, "sample")
    ctx = RuntimeContext(owner_id=owner.id, task_id="task", source_versions={source.id: rev.id})
    other = User(username=uuid4().hex, hashed_password="test", role="user")
    db_session.add(other)
    await db_session.flush()
    kb.user_id = other.id
    await db_session.flush()
    assert source.id not in await capture_source_versions(db_session, owner.id)
    with pytest.raises(LookupError):
        await read_document_range(db_session, ctx, source.id, doc.id, offset=0, limit=1)


async def test_unicode_offsets_and_document_from_other_source(db_session, owner_kb):
    owner, kb = owner_kb
    first, rev, doc = await make_source(db_session, owner.id, kb.id, "first")
    _, _, other_doc = await make_source(db_session, owner.id, kb.id, "second")
    doc.text = "甲乙🙂丙" + "z" * 9000
    await db_session.flush()
    ctx = RuntimeContext(owner_id=owner.id, task_id="task", source_versions={first.id: rev.id})
    part = await read_document_range(db_session, ctx, first.id, doc.id, offset=1, limit=8000)
    assert part.text.startswith("乙🙂丙")
    assert (part.char_start, part.char_end, len(part.text)) == (1, 8001, 8000)
    with pytest.raises(LookupError):
        await read_document_range(db_session, ctx, first.id, other_doc.id, offset=0, limit=1)
    with pytest.raises(LookupError):
        await list_documents(db_session, ctx, first.id, after=other_doc.id)
