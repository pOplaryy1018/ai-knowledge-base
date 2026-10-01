"""Saved answer history and owner-authorized evidence review."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.core.security import get_current_user
from app.models.answer import AnswerEvidence, AnswerRevision, ImpactReview, SavedAnswer
from app.models.source import Source
from app.models.user import User
from app.schemas.answer import AnswerSave, CandidateAccept, ReviewDecision
from app.services.answer_service import (
    accept_candidate,
    answer_payload,
    append_evidence,
    lock_sources,
    owned_answer,
    save_answer,
)

router = APIRouter(tags=["答案复核"])


@router.post("/answers", status_code=201)
async def save(body: AnswerSave, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        saved = await save_answer(session, user.id, str(body.message_id))
        await session.commit()
        return await answer_payload(session, saved)


@router.get("/answers")
async def answers(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                  user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        rows = (await session.execute(select(SavedAnswer).where(SavedAnswer.user_id == user.id)
                                      .order_by(SavedAnswer.created_at.desc()).offset((page - 1) * size).limit(size))).scalars().all()
        return {"items": [await answer_payload(session, row) for row in rows], "page": page, "size": size}


@router.get("/answers/{answer_id}")
async def answer(answer_id: UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        return await answer_payload(session, await owned_answer(session, user.id, str(answer_id)))


@router.post("/answers/{answer_id}/candidates", status_code=201)
async def candidate(answer_id: UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    from app.services.scoped_chat_service import generate_scoped_answer, resolve_scope

    async with async_session() as session:
        saved = await owned_answer(session, user.id, str(answer_id))
        versions = await resolve_scope(session, user.id, list(saved.source_ids))
        question = saved.question
        baseline = saved.accepted_revision_id
    try:
        content, citations = await generate_scoped_answer(question, versions, user.id)
        if not content.strip():
            raise ValueError("模型返回空答案")
    except Exception as error:
        raise HTTPException(502, "候选生成失败，原答案已保留") from error
    async with async_session() as session:
        owner = (await session.execute(select(User).where(User.id == user.id).with_for_update(read=True, key_share=True))).scalar_one_or_none()
        if owner is None:
            raise HTTPException(404, "用户不存在")
        saved = await owned_answer(session, user.id, str(answer_id))
        # Recheck permission after the external generation call.
        await lock_sources(session, user.id, list(saved.source_ids), require_active=True)
        saved = await owned_answer(session, user.id, str(answer_id), lock=True)
        revision = AnswerRevision(saved_answer_id=saved.id, content=content, kind="candidate", source_versions=versions)
        session.add(revision)
        await session.flush()
        await append_evidence(session, revision, citations)
        await session.commit()
        return {"id": revision.id, "content": content, "source_versions": versions, "expected_answer_revision_id": baseline,
                "citations": citations, "kind": "candidate"}


@router.post("/answers/{answer_id}/accept")
async def accept(answer_id: UUID, body: CandidateAccept, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        saved = await accept_candidate(session, user.id, str(answer_id), str(body.candidate_id),
                        str(body.expected_answer_revision_id), {str(key): str(value) for key, value in body.expected_source_versions.items()})
        await session.commit()
        return await answer_payload(session, saved)


@router.get("/reviews")
async def reviews(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                  user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        rows = (await session.execute(select(ImpactReview, SavedAnswer).join(SavedAnswer)
                  .where(SavedAnswer.user_id == user.id, ImpactReview.answer_revision_id == SavedAnswer.accepted_revision_id)
                  .order_by(ImpactReview.created_at.desc()).offset((page - 1) * size).limit(size))).all()
        return {"items": [{"id": review.id, "answer_id": saved.id, "question": saved.question,
                           "decision": review.decision, "note": review.note, "evidence_results": review.evidence_results,
                           "created_at": review.created_at} for review, saved in rows]}


async def owned_review(session: AsyncSession, review_id: str, user_id: str) -> ImpactReview:
    row = (await session.execute(select(ImpactReview).join(SavedAnswer).where(ImpactReview.id == review_id,
                                           SavedAnswer.user_id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "复核记录不存在")
    return row


@router.get("/reviews/{review_id}")
async def review(review_id: UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        record = await owned_review(session, str(review_id), user.id)
        saved = await owned_answer(session, user.id, record.saved_answer_id)
        return {"id": record.id, "decision": record.decision, "note": record.note,
                "checked_answer_revision_id": record.answer_revision_id, "historical_evidence_results": record.evidence_results,
                "answer": await answer_payload(session, saved)}


@router.post("/reviews/{review_id}/decision")
async def decision(review_id: UUID, body: ReviewDecision, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        record = await owned_review(session, str(review_id), user.id)
        saved = await owned_answer(session, user.id, record.saved_answer_id, lock=True)
        if record.answer_revision_id != saved.accepted_revision_id:
            raise HTTPException(409, "当前答案已变化")
        record.decision = body.decision
        record.note = body.note
        await session.commit()
        return {"id": record.id, "decision": record.decision, "note": record.note}


@router.get("/evidence/{evidence_id}")
async def evidence(evidence_id: UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        row = (await session.execute(select(AnswerEvidence)
                                     .join(AnswerRevision, AnswerEvidence.answer_revision_id == AnswerRevision.id)
                                     .join(SavedAnswer, AnswerRevision.saved_answer_id == SavedAnswer.id)
                                     .where(AnswerEvidence.id == str(evidence_id), SavedAnswer.user_id == user.id))).scalar_one_or_none()
        source = await session.get(Source, row.source_id) if row else None
        if row is None or source is None or source.user_id != user.id or source.deleted_at or row.quote is None:
            raise HTTPException(404, "引用证据不可用")
        return {"id": row.id, "source_id": row.source_id, "revision_id": row.revision_id,
                "document_id": row.document_id, "content": row.quote, "locator": row.locator}
