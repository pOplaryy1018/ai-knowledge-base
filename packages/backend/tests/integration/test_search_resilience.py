"""Keyword fallback must still enforce database ownership and version filters."""

import uuid
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision


async def test_keyword_fallback_respects_owner_and_selected_revision(db_session, owner_kb, monkeypatch):
    from app.services import search_service

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revisions = []
    for label in ("old", "current"):
        revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                                  pipeline_version=label, state="ready")
        db_session.add(revision)
        await db_session.flush()
        document = SourceDocument(revision_id=revision.id, logical_path=f"{label}.txt",
                                  text=f"ERROR42 {label}", locator={}, content_hash=uuid.uuid4().hex)
        db_session.add(document)
        await db_session.flush()
        db_session.add(KnowledgeItem(knowledge_base_id=kb.id, revision_id=revision.id,
                                     document_id=document.id, title=label, content=document.text,
                                     source="source_revision", source_metadata={}, status="available"))
        revisions.append(revision)
    await db_session.flush()
    monkeypatch.setattr(search_service, "async_session", async_sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False, join_transaction_mode="create_savepoint"))
    monkeypatch.setattr(search_service, "encode_texts", AsyncMock(side_effect=RuntimeError("unavailable")))

    rows = await search_service.hybrid_search_versions({source.id: revisions[1].id}, "ERROR42", user_id=user.id)
    assert [(row.item.title, row.item.revision_id) for row in rows] == [("current", revisions[1].id)]
    # A failed dense route plus an unauthorized empty keyword route remains an error.
    import pytest
    with pytest.raises(RuntimeError, match="without verified candidates"):
        await search_service.hybrid_search_versions({source.id: revisions[1].id}, "ERROR42", user_id=str(uuid.uuid4()))
