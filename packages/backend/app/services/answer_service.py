"""Append answer history and guard adoption against concurrent source updates."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Conversation, Message
from app.models.answer import AnswerEvidence, AnswerRevision, ImpactReview, SavedAnswer
from app.models.source import Source, SourceChangeEvent, SourceDocument
from app.models.user import User
from app.services.impact_service import inspect_evidence, review_answer_for_event


async def owned_answer(session: AsyncSession, user_id: str, answer_id: str, *, lock: bool = False) -> SavedAnswer:
    stmt = select(SavedAnswer).where(SavedAnswer.id == answer_id, SavedAnswer.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    saved = (await session.execute(stmt)).scalar_one_or_none()
    if saved is None:
        raise HTTPException(404, "答案不存在")
    return saved


async def lock_sources(session: AsyncSession, user_id: str, ids: list[str], *, require_active: bool = False) -> dict[str, str]:
    versions: dict[str, str] = {}
    for source_id in sorted(set(ids)):
        row = (await session.execute(select(Source).where(Source.id == source_id, Source.user_id == user_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if row is None or row.deleted_at or (require_active and row.archived_at):
            raise HTTPException(404, "资料来源不可用")
        if row.current_revision_id:
            versions[row.id] = row.current_revision_id
        elif require_active:
            raise HTTPException(422, "资料来源尚未发布")
    return versions


async def append_evidence(session: AsyncSession, revision: AnswerRevision, citations: list[dict[str, object]]) -> None:
    for citation in citations:
        source_id, revision_id, document_id = (citation.get(key) for key in ("source_id", "revision_id", "document_id"))
        if not all(isinstance(value, str) for value in (source_id, revision_id, document_id)):
            continue
        if revision.source_versions.get(str(source_id)) != revision_id:
            continue
        document = await session.get(SourceDocument, str(document_id))
        quote = citation.get("content")
        locator = citation.get("locator")
        index = citation.get("index")
        if document is None or document.revision_id != revision_id or not isinstance(quote, str) or not quote or quote not in document.text:
            continue
        if not isinstance(locator, dict) or not isinstance(index, int):
            continue
        session.add(AnswerEvidence(answer_revision_id=revision.id, source_id=str(source_id), revision_id=str(revision_id),
                                  document_id=document.id, quote=quote, locator={**locator, "logical_path": document.logical_path},
                                  citation_index=index))
    await session.flush()


async def save_answer(session: AsyncSession, user_id: str, message_id: str) -> SavedAnswer:
    owner = (await session.execute(select(User).where(User.id == user_id).with_for_update(read=True, key_share=True))).scalar_one_or_none()
    if owner is None:
        raise HTTPException(404, "用户不存在")
    row = (await session.execute(select(Message, Conversation).join(Conversation, Message.conversation_id == Conversation.id)
            .where(Message.id == message_id, Conversation.user_id == user_id))).one_or_none()
    if row is None:
        raise HTTPException(404, "消息不存在")
    message, conversation = row
    if message.role != "assistant" or not message.generation_complete or not message.content.strip():
        raise HTTPException(422, "只能保存完整的助手回答")
    ids = list(conversation.source_ids or [])
    heads = await lock_sources(session, user_id, ids)
    # Conversation lock serializes concurrent bookmark requests for the same message.
    await session.execute(select(Conversation).where(Conversation.id == conversation.id).with_for_update())
    existing = (await session.execute(select(SavedAnswer).where(SavedAnswer.origin_message_id == message_id))).scalar_one_or_none()
    if existing:
        return existing
    question = message.question
    if not question:
        question = (await session.execute(select(Message.content).where(Message.conversation_id == conversation.id,
                    Message.role == "user", Message.created_at <= message.created_at).order_by(Message.created_at.desc(), Message.id.desc()).limit(1))).scalar_one_or_none() or "历史回答"
    saved = SavedAnswer(user_id=user_id, question=question, source_ids=ids, origin_message_id=message_id)
    session.add(saved)
    await session.flush()
    revision = AnswerRevision(saved_answer_id=saved.id, content=message.content, source_versions=message.source_versions or {}, origin_message_id=message.id, comparison=message.comparison)
    session.add(revision)
    await session.flush()
    saved.accepted_revision_id = revision.id
    await append_evidence(session, revision, list(message.citations or []))
    for source_id, head in heads.items():
        if revision.source_versions.get(source_id) != head:
            source = await session.get(Source, source_id)
            publication_id = source.current_publication_id if source else None
            event = (await session.execute(select(SourceChangeEvent).where(SourceChangeEvent.source_id == source_id,
                    SourceChangeEvent.publication_id == publication_id))).scalar_one_or_none()
            if event:
                await review_answer_for_event(session, saved, event)
    return saved


async def answer_payload(session: AsyncSession, saved: SavedAnswer) -> dict[str, Any]:
    revision = await session.get(AnswerRevision, saved.accepted_revision_id) if saved.accepted_revision_id else None
    evidence = (await session.execute(select(AnswerEvidence).where(AnswerEvidence.answer_revision_id == saved.accepted_revision_id))).scalars().all()
    results = [{**(await inspect_evidence(session, row, saved.user_id)), "citation_index": row.citation_index,
                "old_revision_id": row.revision_id, "document_id": row.document_id} for row in evidence]
    states = {result["state"] for result in results}
    status = "untracked" if not evidence else ("unavailable" if "unavailable" in states else
             "needs_review" if states & {"changed", "missing", "ambiguous"} else "unchanged")
    history = (await session.execute(select(AnswerRevision).where(AnswerRevision.saved_answer_id == saved.id).order_by(AnswerRevision.created_at))).scalars().all()
    history_payload = []
    for row in history:
        citations = []
        if row.comparison:
            entries = (await session.execute(select(AnswerEvidence).where(
                AnswerEvidence.answer_revision_id == row.id,
            ))).scalars().all()
            for entry in entries:
                checked = await inspect_evidence(session, entry, saved.user_id)
                if checked["old_text"] and entry.revision_id and entry.document_id:
                    citations.append({"index": entry.citation_index, "source_id": entry.source_id,
                                      "revision_id": entry.revision_id, "document_id": entry.document_id,
                                      "content": checked["old_text"], "locator": checked["old_locator"]})
        history_payload.append({"id": row.id, "content": row.content, "kind": row.kind,
                                "source_versions": row.source_versions, "created_at": row.created_at,
                                "comparison": row.comparison, "citations": citations})
    return {"id": saved.id, "question": saved.question, "source_ids": saved.source_ids,
            "accepted_revision_id": saved.accepted_revision_id, "content": revision.content if revision else "",
            "source_versions": revision.source_versions if revision else {}, "status": status,
            "comparison": revision.comparison if revision else None,
            "evidence": results, "created_at": saved.created_at,
            "versions": history_payload}


async def accept_candidate(session: AsyncSession, user_id: str, answer_id: str, candidate_id: str,
                           expected_answer_revision_id: str, expected_source_versions: dict[str, str]) -> SavedAnswer:
    saved = await owned_answer(session, user_id, answer_id)
    heads = await lock_sources(session, user_id, list(saved.source_ids), require_active=True)
    saved = await owned_answer(session, user_id, answer_id, lock=True)
    candidate = await session.get(AnswerRevision, candidate_id)
    if candidate is None or candidate.saved_answer_id != saved.id or candidate.kind != "candidate":
        raise HTTPException(404, "候选答案不存在")
    if saved.accepted_revision_id != expected_answer_revision_id or heads != expected_source_versions or candidate.source_versions != heads:
        raise HTTPException(409, "资料或答案版本已变化，请重新复核")
    previous = saved.accepted_revision_id
    saved.accepted_revision_id = candidate.id
    reviews = (await session.execute(select(ImpactReview).where(ImpactReview.saved_answer_id == saved.id,
                                    ImpactReview.answer_revision_id == previous))).scalars().all()
    for review in reviews:
        review.decision = "adopted"
    await session.flush()
    return saved
