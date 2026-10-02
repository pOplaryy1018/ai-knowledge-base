"""Direct evidence checks; event retries never decide factual correctness."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.models.answer import AnswerEvidence, ImpactReview, SavedAnswer
from app.models.source import Source, SourceChangeEvent, SourceDocument, SourceRevision
from app.services.evidence_matching import match_evidence
from app.services.source_extraction import LocatedText


async def inspect_evidence(session: AsyncSession, evidence: AnswerEvidence, user_id: str) -> dict[str, Any]:
    source = await session.get(Source, evidence.source_id)
    result: dict[str, Any] = {"evidence_id": evidence.id, "source_id": evidence.source_id,
                              "old_text": evidence.quote, "old_locator": evidence.locator}
    if source is None or source.user_id != user_id or source.deleted_at:
        return {**result, "old_text": None, "old_locator": {}, "state": "unavailable", "current_text": None, "locator": None}
    if not evidence.quote or not source.current_revision_id:
        return {**result, "state": "unavailable", "current_text": None, "locator": None}
    rows = (await session.execute(select(SourceDocument).where(SourceDocument.revision_id == source.current_revision_id))).scalars().all()
    path = evidence.locator.get("logical_path")
    matching = [row for row in rows if row.logical_path == path]
    if source.kind == "image":
        old = await session.get(SourceRevision, evidence.revision_id) if evidence.revision_id else None
        current = await session.get(SourceRevision, source.current_revision_id)
        origin = evidence.locator.get("origin")
        old_hash = evidence.locator.get("image_hash")
        current_hash = current.manifest.get("image_hash") if current else None
        channel_paths = {"image_ocr": "ocr_text", "image_ocr_correction": "ocr_correction", "manual_description": "manual_description"}
        result.update(old_revision_id=evidence.revision_id, current_revision_id=source.current_revision_id)
        if (not isinstance(origin, str) or origin not in channel_paths
                or not isinstance(path, str) or path != channel_paths[origin]
                or not isinstance(old_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", old_hash)
                or old is None or old.source_id != source.id or old.manifest.get("image_hash") != old_hash
                or current is None or current.source_id != source.id
                or not isinstance(current_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", current_hash)):
            return {**result, "state": "unavailable", "reason": "image_untracked", "current_text": None, "locator": None}
        matching = [row for row in matching if row.locator.get("origin") == origin]
        documents = [LocatedText(row.logical_path, row.text, row.locator) for row in matching]
        match = match_evidence(evidence.quote, documents, evidence.locator)
        current_text = match.current_text
        locator = match.locator
        if matching and current_text is None and match.state != "ambiguous":
            start = evidence.locator.get("char_start", 0)
            offset = start if isinstance(start, int) else 0
            current_text = matching[0].text[offset:offset + len(evidence.quote)]
            locator = {**matching[0].locator, "logical_path": matching[0].logical_path}
        if old_hash != current_hash:
            return {**result, "state": "changed", "reason": "image_changed", "current_text": current_text, "locator": locator}
        return {**result, "state": match.state, "current_text": current_text, "locator": locator}
    # Missing path may be a moved page/paragraph; global exact matching is conservative.
    documents = [LocatedText(row.logical_path, row.text, row.locator) for row in matching or rows]
    match = match_evidence(evidence.quote, documents, evidence.locator)
    state = "missing" if path and not matching and match.state == "changed" else match.state
    current_text = match.current_text
    if current_text is None and matching:
        start = evidence.locator.get("char_start", 0)
        offset = start if isinstance(start, int) else 0
        current_text = matching[0].text[offset:offset + len(evidence.quote)]
    return {**result, "state": state, "locator": match.locator,
            "current_text": current_text, "current_revision_id": source.current_revision_id}


async def review_answer_for_event(session: AsyncSession, saved: SavedAnswer, event: SourceChangeEvent) -> ImpactReview:
    if saved.accepted_revision_id is None:
        raise ValueError("Saved answer has no accepted revision")
    existing = (await session.execute(select(ImpactReview).where(ImpactReview.event_id == event.id,
                ImpactReview.saved_answer_id == saved.id, ImpactReview.answer_revision_id == saved.accepted_revision_id))).scalar_one_or_none()
    if existing:
        return existing
    evidence = (await session.execute(select(AnswerEvidence).where(
        AnswerEvidence.answer_revision_id == saved.accepted_revision_id, AnswerEvidence.source_id == event.source_id))).scalars().all()
    results = [await inspect_evidence(session, row, saved.user_id) for row in evidence]
    review = ImpactReview(event_id=event.id, saved_answer_id=saved.id, answer_revision_id=saved.accepted_revision_id,
                          evidence_results=results)
    session.add(review)
    await session.flush()
    return review


async def process_impact_events() -> None:
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        events = (await session.execute(select(SourceChangeEvent).where(or_(SourceChangeEvent.state.in_(["pending", "failed"]),
                 (SourceChangeEvent.state == "processing") & (SourceChangeEvent.lease_until < now)))
                 .order_by(SourceChangeEvent.created_at).limit(20).with_for_update(skip_locked=True))).scalars().all()
        ids = [event.id for event in events]
        for claimed in events:
            claimed.state = "processing"
            claimed.lease_until = now + timedelta(minutes=5)
            claimed.attempts += 1
        await session.commit()
    for event_id in ids:
        try:
            async with async_session() as session:
                event = await session.get(SourceChangeEvent, event_id)
                if event is None:
                    continue
                # Source lock serializes repeated event processing with save/accept.
                await session.execute(select(Source).where(Source.id == event.source_id).with_for_update())
                answers = (await session.execute(select(SavedAnswer).join(AnswerEvidence,
                        AnswerEvidence.answer_revision_id == SavedAnswer.accepted_revision_id)
                        .where(AnswerEvidence.source_id == event.source_id).distinct())).scalars().all()
                for saved in answers:
                    locked = (await session.execute(select(SavedAnswer).where(SavedAnswer.id == saved.id).with_for_update())).scalar_one()
                    await review_answer_for_event(session, locked, event)
                event.state = "done"
                event.lease_until = None
                event.error = None
                await session.commit()
        except Exception:
            async with async_session() as session:
                event = await session.get(SourceChangeEvent, event_id)
                if event:
                    event.state = "failed"
                    event.error = "复核失败，将自动重试"
                    event.lease_until = None
                    await session.commit()
