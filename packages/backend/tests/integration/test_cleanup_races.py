
from sqlalchemy import select

from app.models.agent import Conversation, Message
from app.models.source import Source, SourceRevision
from tests.integration.test_evidence_lifecycle import lifecycle_client as lifecycle_client


async def test_persist_after_source_deletion_does_not_restore_quotes(lifecycle_client, db_session):
    from app.services.scoped_chat_service import persist_answer
    from app.services.source_cleanup import redact_source

    _, user, kb = lifecycle_client
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="private")
    conversation = Conversation(user_id=user.id)
    db_session.add_all([source, conversation])
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash="private", pipeline_version="test", state="ready")
    db_session.add(revision)
    await db_session.flush()
    source.current_revision_id = revision.id
    citation = {"index": 1, "source_id": source.id, "content": "private quote", "quote": "private quote", "locator": {"line_start": 1}}
    await redact_source(db_session, source.id)
    await persist_answer(conversation.id, "q", {source.id: revision.id}, "answer", [citation], True)
    row = (await db_session.execute(select(Message).where(Message.conversation_id == conversation.id))).scalar_one()
    assert row.citations[0]["content"] is None
    assert citation["content"] is None


async def test_user_cleanup_preserves_failed_file_deletion_intent(db_session, owner_kb, tmp_path):
    from app.models.asset_cleanup import AssetCleanup
    from app.services.source_cleanup import purge_user_history

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="private")
    db_session.add(source)
    await db_session.flush()
    path = tmp_path / "original.txt"
    path.write_text("private")
    db_session.add(SourceRevision(source_id=source.id, raw_hash="hash", pipeline_version="test", file_path=str(path)))
    await db_session.flush()
    await purge_user_history(db_session, user.id)
    intents = (await db_session.execute(select(AssetCleanup))).scalars().all()
    assert [intent.file_path for intent in intents] == [str(path)]
    assert path.exists()
