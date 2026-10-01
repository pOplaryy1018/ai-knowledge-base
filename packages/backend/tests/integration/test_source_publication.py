import hashlib

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.source import Source, SourceChangeEvent, SourceDocument, SourceRevision
from app.services.source_extraction import LocatedText


async def test_publish_keeps_old_documents_and_creates_one_event(db_session, owner_kb):
    from app.services.source_publication import publish_revision, store_revision_documents

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="sample")
    db_session.add(source)
    await db_session.flush()
    previous = None
    for body in ["old policy", "new policy"]:
        revision = SourceRevision(source_id=source.id, raw_hash=hashlib.sha256(body.encode()).hexdigest(), pipeline_version="test")
        db_session.add(revision)
        await db_session.flush()
        await store_revision_documents(db_session, source, revision, [LocatedText("text", body, {"type": "text"})], [[1.0] * 1024])
        event = await publish_revision(db_session, source.id, revision.id, previous)
        assert (await publish_revision(db_session, source.id, revision.id, previous)).id == event.id
        previous = revision.id
    docs = (await db_session.execute(select(SourceDocument).join(SourceRevision).where(SourceRevision.source_id == source.id))).scalars().all()
    assert {d.text for d in docs} == {"old policy", "new policy"}
    assert len((await db_session.execute(select(SourceChangeEvent).where(SourceChangeEvent.source_id == source.id))).scalars().all()) == 2


async def test_bad_revision_cannot_replace_head(db_session, owner_kb):
    from app.services.source_publication import publish_revision

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="sample")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash="hash", pipeline_version="test", state="failed")
    db_session.add(revision)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await publish_revision(db_session, source.id, revision.id, None)
    assert exc.value.status_code == 409
    assert source.current_revision_id is None

async def test_rollback_creates_distinct_publications(db_session, owner_kb):
    from app.services.source_publication import publish_revision
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="rollback")
    db_session.add(source)
    await db_session.flush()
    revisions = [SourceRevision(source_id=source.id, raw_hash=h, pipeline_version="test", state="ready") for h in ["a", "b"]]
    db_session.add_all(revisions)
    await db_session.flush()
    a, b = revisions
    first = await publish_revision(db_session, source.id, a.id, None)
    middle = await publish_revision(db_session, source.id, b.id, a.id)
    last = await publish_revision(db_session, source.id, a.id, b.id)
    assert first.id != last.id
    assert first.publication_id != last.publication_id
    assert (await publish_revision(db_session, source.id, a.id, b.id)).id == last.id
    from app.models.source_publication import SourcePublication
    publications = (await db_session.execute(select(SourcePublication).where(SourcePublication.source_id == source.id).order_by(SourcePublication.sequence))).scalars().all()
    assert [p.revision_id for p in publications] == [a.id, b.id, a.id]
    assert [p.sequence for p in publications] == [1, 2, 3]
    assert publications[2].previous_publication_id == middle.publication_id
    assert source.current_publication_id == last.publication_id
