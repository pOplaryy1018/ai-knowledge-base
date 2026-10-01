from app.models.answer import AnswerEvidence, AnswerRevision, SavedAnswer
from app.models.source import Source, SourceDocument, SourceRevision
from app.services.source_publication import publish_revision


async def test_event_review_is_idempotent_and_marks_changed_quote(db_session, owner_kb):
    from app.services.impact_service import review_answer_for_event

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="policy")
    db_session.add(source)
    await db_session.flush()
    revisions = []
    for name in ["before", "after"]:
        r = SourceRevision(source_id=source.id, raw_hash=name, pipeline_version="test", state="ready")
        db_session.add(r)
        await db_session.flush()
        d = SourceDocument(revision_id=r.id, logical_path="text", text=name, locator={}, content_hash=name)
        db_session.add(d)
        await db_session.flush()
        revisions.append((r, d))
    first, second = revisions
    source.current_revision_id = first[0].id
    saved = SavedAnswer(user_id=user.id, question="q", source_ids=[source.id])
    db_session.add(saved)
    await db_session.flush()
    answer = AnswerRevision(saved_answer_id=saved.id, content="before [1]", source_versions={source.id: first[0].id})
    db_session.add(answer)
    await db_session.flush()
    saved.accepted_revision_id = answer.id
    db_session.add(AnswerEvidence(answer_revision_id=answer.id, source_id=source.id, revision_id=first[0].id,
                                  document_id=first[1].id, quote="before", locator={"logical_path": "text"}, citation_index=1))
    await db_session.flush()
    event = await publish_revision(db_session, source.id, second[0].id, first[0].id)
    one = await review_answer_for_event(db_session, saved, event)
    two = await review_answer_for_event(db_session, saved, event)
    assert one.id == two.id
    assert one.evidence_results[0]["state"] == "changed"

async def test_late_event_reviews_live_head_after_rollback(db_session, owner_kb):
    from app.services.impact_service import review_answer_for_event
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="late event")
    db_session.add(source)
    await db_session.flush()
    revisions = []
    for text in ["before", "after"]:
        revision = SourceRevision(source_id=source.id, raw_hash=text, pipeline_version="test", state="ready")
        db_session.add(revision)
        await db_session.flush()
        document = SourceDocument(revision_id=revision.id, logical_path="text", text=text, locator={}, content_hash=text)
        db_session.add(document)
        await db_session.flush()
        revisions.append((revision, document))
    a, b = revisions
    await publish_revision(db_session, source.id, a[0].id, None)
    saved = SavedAnswer(user_id=user.id, question="q", source_ids=[source.id])
    db_session.add(saved)
    await db_session.flush()
    answer = AnswerRevision(saved_answer_id=saved.id, content="before", source_versions={source.id: a[0].id})
    db_session.add(answer)
    await db_session.flush()
    saved.accepted_revision_id = answer.id
    evidence = AnswerEvidence(answer_revision_id=answer.id, source_id=source.id, revision_id=a[0].id, document_id=a[1].id, quote="before", locator={"logical_path": "text"}, citation_index=1)
    db_session.add(evidence)
    await db_session.flush()
    old_event = await publish_revision(db_session, source.id, b[0].id, a[0].id)
    rollback_event = await publish_revision(db_session, source.id, a[0].id, b[0].id)
    late = await review_answer_for_event(db_session, saved, old_event)
    rollback = await review_answer_for_event(db_session, saved, rollback_event)
    assert late.evidence_results[0]["state"] == "unchanged"
    assert rollback.evidence_results[0]["state"] == "unchanged"
    assert late.event_id != rollback.event_id
    assert evidence.revision_id == a[0].id and evidence.quote == "before"
