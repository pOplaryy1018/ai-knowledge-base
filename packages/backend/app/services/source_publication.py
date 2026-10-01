"""Stage immutable documents and atomically expose a ready source revision."""

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceChangeEvent, SourceDocument, SourceRevision
from app.models.source_publication import SourcePublication
from app.services.source_extraction import LocatedText


def document_chunks(documents: list[LocatedText]) -> list[LocatedText]:
    chunks: list[LocatedText] = []
    for document in documents:
        for start in range(0, len(document.text), 850):
            end = min(start + 1000, len(document.text))
            content = document.text[start:end]
            if not content.strip():
                continue
            chunks.append(LocatedText(document.logical_path, content, {
                **document.locator, "logical_path": document.logical_path,
                "char_start": start, "char_end": end,
                "line_start": document.text.count("\n", 0, start) + 1,
                "line_end": document.text.count("\n", 0, end) + 1,
            }))
            if end == len(document.text):
                break
    return chunks


async def store_revision_documents(session: AsyncSession, source: Source, revision: SourceRevision,
                                   documents: list[LocatedText], vectors: list[list[float]]) -> None:
    chunks = document_chunks(documents)
    if not chunks or len(chunks) != len(vectors) or any(len(v) != 1024 for v in vectors):
        raise ValueError("Nonempty chunks and 1024-dimensional embeddings are required")
    if revision.state != "staging" or source.knowledge_base_id is None:
        raise HTTPException(409, "版本不可写入")
    document_ids: dict[str, str] = {}
    for document in documents:
        row = SourceDocument(revision_id=revision.id, logical_path=document.logical_path,
                             text=document.text, locator=document.locator,
                             content_hash=hashlib.sha256(document.text.encode()).hexdigest())
        session.add(row)
        await session.flush()
        document_ids[document.logical_path] = row.id
    for chunk, vector in zip(chunks, vectors, strict=True):
        session.add(KnowledgeItem(knowledge_base_id=source.knowledge_base_id, revision_id=revision.id,
                                 document_id=document_ids[chunk.logical_path], title=f"{source.name} · {chunk.logical_path}",
                                 content=chunk.text, embedding=vector, locator=chunk.locator,
                                 source="source_revision", source_metadata={"source_id": source.id}))
    revision.state = "ready"
    await session.flush()


async def publish_revision(session: AsyncSession, source_id: str, revision_id: str,
                           expected_head: str | None) -> SourceChangeEvent:
    source = (await session.execute(select(Source).where(Source.id == source_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    revision = await session.get(SourceRevision, revision_id)
    if source is None or source.deleted_at or source.archived_at or revision is None or revision.source_id != source_id:
        raise HTTPException(404, "资料来源不可用")
    existing = (await session.execute(select(SourceChangeEvent).where(
        SourceChangeEvent.publication_id == source.current_publication_id))).scalar_one_or_none() if source.current_publication_id else None
    if source.current_revision_id == revision_id and existing is not None:
        return existing
    if source.current_revision_id != expected_head or revision.state != "ready":
        raise HTTPException(409, "资料版本已变化或尚未就绪")
    previous = await session.get(SourcePublication, source.current_publication_id) if source.current_publication_id else None
    publication = SourcePublication(source_id=source.id, revision_id=revision.id,
        previous_publication_id=source.current_publication_id, sequence=previous.sequence + 1 if previous else 1)
    session.add(publication)
    await session.flush()
    source.current_revision_id = revision_id
    source.current_publication_id = publication.id
    if revision.published_at is None:
        revision.published_at = datetime.now(timezone.utc)
    event = SourceChangeEvent(source_id=source_id, old_revision_id=expected_head,
                              new_revision_id=revision_id, publication_id=publication.id)
    session.add(event)
    await session.flush()
    return event
