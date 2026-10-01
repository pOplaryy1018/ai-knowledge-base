"""Exercise constraints and history in the isolated PostgreSQL database."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.agent import Conversation
from app.models.answer import AnswerEvidence, AnswerRevision, ImpactReview, SavedAnswer
from app.models.knowledge import KnowledgeItem
from app.models.source import (
    Source,
    SourceChangeEvent,
    SourceDocument,
    SourceRevision,
    SourceSyncTask,
)


async def snapshot(db_session, owner_kb):
    owner, kb = owner_kb
    source = Source(user_id=owner.id, knowledge_base_id=kb.id, name="Test")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash="v1", pipeline_version="1", state="ready")
    db_session.add(revision)
    await db_session.flush()
    document = SourceDocument(revision_id=revision.id, logical_path="page/1", text="Original", locator={"page": 1}, content_hash="v1")
    db_session.add(document)
    await db_session.flush()
    source.current_revision_id = revision.id
    return owner, kb, source, revision, document


async def test_legacy_item_and_agentless_conversation(db_session, owner_kb):
    owner, kb = owner_kb
    item = KnowledgeItem(knowledge_base_id=kb.id, title="Legacy", content="Legacy")
    conversation = Conversation(user_id=owner.id)
    db_session.add_all([item, conversation])
    await db_session.flush()
    assert item.revision_id is None and item.document_id is None
    assert conversation.agent_id is None and conversation.source_ids == []


async def test_revision_event_and_review_idempotency(db_session, owner_kb):
    owner, kb, source, revision, document = await snapshot(db_session, owner_kb)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(SourceRevision(source_id=source.id, raw_hash="v1", pipeline_version="1"))
            await db_session.flush()
    event = SourceChangeEvent(source_id=source.id, new_revision_id=revision.id)
    answer = SavedAnswer(user_id=owner.id, question="What?", source_ids=[source.id])
    db_session.add_all([event, answer])
    await db_session.flush()
    answer_revision = AnswerRevision(saved_answer_id=answer.id, content="Original", source_versions={source.id: revision.id})
    db_session.add(answer_revision)
    await db_session.flush()
    review = ImpactReview(event_id=event.id, saved_answer_id=answer.id, answer_revision_id=answer_revision.id)
    db_session.add(review)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(SourceChangeEvent(source_id=source.id, new_revision_id=revision.id))
            await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(ImpactReview(event_id=event.id, saved_answer_id=answer.id, answer_revision_id=answer_revision.id))
            await db_session.flush()


async def test_publication_and_document_cleanup_preserve_evidence(db_session, owner_kb):
    owner, kb, source, revision, document = await snapshot(db_session, owner_kb)
    answer = SavedAnswer(user_id=owner.id, question="What?", source_ids=[source.id])
    db_session.add(answer)
    await db_session.flush()
    answer_revision = AnswerRevision(saved_answer_id=answer.id, content="Original", source_versions={source.id: revision.id})
    db_session.add(answer_revision)
    await db_session.flush()
    evidence = AnswerEvidence(answer_revision_id=answer_revision.id, source_id=source.id, revision_id=revision.id, document_id=document.id, quote="Original", locator={"page": 1}, citation_index=1)
    replacement = SourceRevision(source_id=source.id, raw_hash="v2", pipeline_version="1", state="ready")
    db_session.add_all([evidence, replacement])
    await db_session.flush()
    source.current_revision_id = replacement.id
    await db_session.flush()
    assert (await db_session.execute(select(SourceDocument).where(SourceDocument.id == document.id))).scalar_one().text == "Original"
    await db_session.delete(document)
    await db_session.flush()
    await db_session.refresh(evidence)
    assert evidence.document_id is None and evidence.quote == "Original"


async def test_only_one_active_sync_per_source(db_session, owner_kb):
    owner, kb, source, revision, document = await snapshot(db_session, owner_kb)
    task = SourceSyncTask(source_id=source.id, user_id=owner.id, revision_id=revision.id)
    db_session.add(task)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(SourceSyncTask(source_id=source.id, user_id=owner.id, status="processing"))
            await db_session.flush()
    task.status = "completed"
    await db_session.flush()
    db_session.add(SourceSyncTask(source_id=source.id, user_id=owner.id))
    await db_session.flush()
