from app.models.answer import AnswerEvidence, AnswerRevision, SavedAnswer
from app.models.source import Source, SourceDocument, SourceRevision
from tests.integration.test_evidence_lifecycle import lifecycle_client as lifecycle_client


async def test_source_cleanup_redacts_evidence_and_preserves_answer(db_session, owner_kb):
    from app.services.source_cleanup import redact_source

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="private")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash="hash", pipeline_version="test", state="ready")
    db_session.add(revision)
    await db_session.flush()
    document = SourceDocument(revision_id=revision.id, logical_path="text", text="private fact", locator={}, content_hash="hash")
    db_session.add(document)
    await db_session.flush()
    saved = SavedAnswer(user_id=user.id, question="question", source_ids=[source.id])
    db_session.add(saved)
    await db_session.flush()
    answer = AnswerRevision(saved_answer_id=saved.id, content="my answer", source_versions={source.id: revision.id})
    db_session.add(answer)
    await db_session.flush()
    evidence = AnswerEvidence(answer_revision_id=answer.id, source_id=source.id, revision_id=revision.id,
                              document_id=document.id, quote=document.text, locator={}, citation_index=1)
    db_session.add(evidence)
    await db_session.flush()
    await redact_source(db_session, source.id)
    await db_session.refresh(evidence)
    assert evidence.quote is None
    assert source.deleted_at is not None
    assert answer.content == "my answer"


async def test_cross_user_apis_do_not_expose_sources_or_saved_answers(lifecycle_client):
    import uuid

    from app.core.security import get_current_user
    from app.main import app
    from app.models.user import User

    client, _, kb = lifecycle_client
    created = (await client.post("/api/sources", json={"name": "private", "knowledge_base_id": kb.id})).json()
    app.dependency_overrides[get_current_user] = lambda: User(id=str(uuid.uuid4()), username="other", hashed_password="test", role="user")
    assert (await client.get(f'/api/sources/{created["id"]}/revisions')).status_code == 404
    assert (await client.get("/api/sources")).json()["items"] == []
    assert (await client.post("/api/chat/scoped", json={"question": "q", "source_ids": [created["id"]]})).status_code == 404
