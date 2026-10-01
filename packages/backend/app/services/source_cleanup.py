"""Redact tracked evidence before removing a source or its owning collection."""

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Message
from app.models.answer import AnswerEvidence, ImpactReview, SavedAnswer
from app.models.asset_cleanup import AssetCleanup
from app.models.knowledge import KnowledgeItem
from app.models.source import (
    Source,
    SourceChangeEvent,
    SourceDocument,
    SourceRevision,
    SourceSyncTask,
)
from app.services.file_storage import remove_uploads


async def queue_cleanup(session: AsyncSession, paths: list[str]) -> None:
    for path in set(paths):
        existing = (await session.execute(select(AssetCleanup.id).where(AssetCleanup.file_path == path))).scalar_one_or_none()
        if existing is None:
            session.add(AssetCleanup(file_path=path))
            await session.flush()


async def redact_source(session: AsyncSession, source_id: str) -> list[str]:
    source = (await session.execute(select(Source).where(Source.id == source_id).with_for_update())).scalar_one_or_none()
    if source is None:
        return []
    source.deleted_at = datetime.now(timezone.utc)
    source.current_revision_id = None
    source.active_task_id = None
    revisions = (await session.execute(select(SourceRevision).where(SourceRevision.source_id == source_id))).scalars().all()
    ids = [revision.id for revision in revisions]
    paths = [revision.file_path for revision in revisions if revision.file_path]
    await queue_cleanup(session, paths)
    await session.execute(update(SourceSyncTask).where(SourceSyncTask.source_id == source_id, SourceSyncTask.status.in_(["pending", "processing"]))
                          .values(status="failed", stage="deleted", error="资料来源已删除"))
    await session.execute(update(AnswerEvidence).where(AnswerEvidence.source_id == source_id).values(quote=None, locator={}))
    await session.execute(delete(KnowledgeItem).where(KnowledgeItem.revision_id.in_(ids)))
    await session.execute(delete(SourceDocument).where(SourceDocument.revision_id.in_(ids)))
    for revision in revisions:
        revision.filename = None
    # Citation metadata and historical diffs also contain copies of the original text.
    messages = (await session.execute(select(Message).where(Message.citations.isnot(None)))).scalars().all()
    for message in messages:
        citations = list(message.citations or [])
        if any(citation.get("source_id") == source_id for citation in citations):
            message.citations = [{**citation, "content": None, "quote": None, "locator": {}, "unavailable": True}
                                if citation.get("source_id") == source_id else citation for citation in citations]
    reviews = (await session.execute(select(ImpactReview).join(SourceChangeEvent).where(SourceChangeEvent.source_id == source_id))).scalars().all()
    for review in reviews:
        review.evidence_results = [{**result, "old_text": None, "current_text": None, "old_locator": {}, "locator": None,
                                   "state": "unavailable"} for result in review.evidence_results]
    await session.flush()
    return paths


async def redact_collection(session: AsyncSession, kb_id: str) -> list[str]:
    sources = (await session.execute(select(Source).where(Source.knowledge_base_id == kb_id).order_by(Source.id))).scalars().all()
    paths: list[str] = []
    for source in sources:
        paths.extend(await redact_source(session, source.id))
        source.knowledge_base_id = None
    await session.flush()
    return paths


async def purge_user_history(session: AsyncSession, user_id: str) -> list[str]:
    sources = (await session.execute(select(Source).where(Source.user_id == user_id).order_by(Source.id))).scalars().all()
    paths: list[str] = []
    for source in sources:
        paths.extend(await redact_source(session, source.id))
    await session.execute(delete(SavedAnswer).where(SavedAnswer.user_id == user_id))
    for source in sources:
        await session.execute(delete(SourceSyncTask).where(SourceSyncTask.source_id == source.id))
        await session.execute(delete(SourceChangeEvent).where(SourceChangeEvent.source_id == source.id))
        await session.execute(delete(SourceRevision).where(SourceRevision.source_id == source.id))
        await session.execute(delete(Source).where(Source.id == source.id))
    await session.flush()
    return paths


async def retry_source_cleanup(session: AsyncSession) -> None:
    rows = (await session.execute(select(AssetCleanup).limit(100).with_for_update(skip_locked=True))).scalars().all()
    from pathlib import Path

    from app.services.file_storage import LEGACY_UPLOAD_ROOT, UPLOAD_ROOT

    for intent in rows:
        path = Path(intent.file_path).resolve()
        if not any(path.is_relative_to(root.resolve()) for root in (UPLOAD_ROOT, LEGACY_UPLOAD_ROOT)):
            continue
        remove_uploads([str(path)])
        if not path.exists():
            await session.delete(intent)
            await session.execute(update(SourceRevision).where(SourceRevision.file_path == intent.file_path).values(file_path=None))
    await session.commit()
