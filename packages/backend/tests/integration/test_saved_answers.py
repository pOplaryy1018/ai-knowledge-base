import pytest
from fastapi import HTTPException

from app.models.agent import Conversation, Message
from app.models.source import Source


async def test_saving_legacy_answer_is_untracked_and_idempotent(db_session, owner_kb):
    from app.services.answer_service import answer_payload, save_answer

    user, _ = owner_kb
    conversation = Conversation(user_id=user.id, source_ids=[])
    db_session.add(conversation)
    await db_session.flush()
    message = Message(conversation_id=conversation.id, role="assistant", content="legacy", question="question", citations=[{"index": 1, "knowledge_title": "old"}])
    db_session.add(message)
    await db_session.flush()
    saved = await save_answer(db_session, user.id, message.id)
    assert (await save_answer(db_session, user.id, message.id)).id == saved.id
    assert (await answer_payload(db_session, saved))["status"] == "untracked"


async def test_incomplete_response_cannot_be_saved(db_session, owner_kb):
    from app.services.answer_service import save_answer

    user, _ = owner_kb
    conversation = Conversation(user_id=user.id)
    db_session.add(conversation)
    await db_session.flush()
    message = Message(conversation_id=conversation.id, role="assistant", content="partial", generation_complete=False)
    db_session.add(message)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await save_answer(db_session, user.id, message.id)
    assert exc.value.status_code == 422


async def test_accept_checks_source_head_even_without_event_processing(db_session, owner_kb):
    from app.models.answer import AnswerRevision, SavedAnswer
    from app.models.source import SourceRevision
    from app.services.answer_service import accept_candidate

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="policy")
    db_session.add(source)
    await db_session.flush()
    v1 = SourceRevision(source_id=source.id, raw_hash="v1", pipeline_version="test", state="ready")
    v2 = SourceRevision(source_id=source.id, raw_hash="v2", pipeline_version="test", state="ready")
    db_session.add_all([v1, v2])
    await db_session.flush()
    source.current_revision_id = v2.id
    saved = SavedAnswer(user_id=user.id, question="q", source_ids=[source.id])
    db_session.add(saved)
    await db_session.flush()
    original = AnswerRevision(saved_answer_id=saved.id, content="old", source_versions={source.id: v1.id})
    candidate = AnswerRevision(saved_answer_id=saved.id, content="candidate", kind="candidate", source_versions={source.id: v1.id})
    db_session.add_all([original, candidate])
    await db_session.flush()
    saved.accepted_revision_id = original.id
    with pytest.raises(HTTPException) as exc:
        await accept_candidate(db_session, user.id, saved.id, candidate.id, original.id, {source.id: v1.id})
    assert exc.value.status_code == 409
    assert saved.accepted_revision_id == original.id
