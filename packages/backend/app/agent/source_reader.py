"""Owner-scoped version snapshots and bounded reads of extracted source text."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Integer, String, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.agent.contracts import RuntimeContext
from app.models.knowledge import KnowledgeBase
from app.models.source import Source, SourceDocument, SourceRevision


@dataclass(frozen=True)
class DocumentPage:
    document_ids: list[str]
    next_cursor: str | None


@dataclass(frozen=True)
class DocumentRange:
    source_id: str
    revision_id: str
    document_id: str
    char_start: int
    char_end: int
    text: str


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise LookupError("source unavailable") from None


async def capture_source_versions(session: AsyncSession, owner_id: str) -> dict[str, str]:
    owner_id = _uuid(owner_id)
    result = await session.execute(
        select(Source.id, SourceRevision.id)
        .join(SourceRevision, and_(Source.current_revision_id == SourceRevision.id,
                                   SourceRevision.source_id == Source.id))
        .where(Source.user_id == owner_id, Source.archived_at.is_(None), Source.deleted_at.is_(None),
               SourceRevision.state == "ready", _knowledge_access(owner_id))
    )
    return dict(result.all())


def _scope(context: RuntimeContext, source_id: str) -> tuple[str, str, str]:
    owner_id = _uuid(context.owner_id)
    source_id = _uuid(source_id)
    revision_id = context.source_versions.get(source_id)
    if revision_id is None:
        raise LookupError("source unavailable")
    return owner_id, source_id, _uuid(revision_id)


def _knowledge_access(owner_id: str) -> ColumnElement[bool]:
    return or_(Source.knowledge_base_id.is_(None),
               select(KnowledgeBase.id).where(KnowledgeBase.id == Source.knowledge_base_id,
                                              KnowledgeBase.user_id == owner_id).exists())


def _visible(owner_id: str, source_id: str, revision_id: str) -> tuple[ColumnElement[bool], ...]:
    return (Source.id == source_id, Source.user_id == owner_id, Source.archived_at.is_(None),
            Source.deleted_at.is_(None), SourceRevision.id == revision_id,
            SourceRevision.source_id == Source.id, SourceRevision.state == "ready", _knowledge_access(owner_id))


async def list_documents(
    session: AsyncSession, context: RuntimeContext, source_id: str, *, limit: int = 50, after: str | None = None,
) -> DocumentPage:
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("invalid page limit")
    owner_id, source_id, revision_id = _scope(context, source_id)
    query = (select(SourceDocument.id)
             .join(SourceRevision, SourceDocument.revision_id == SourceRevision.id)
             .join(Source, SourceRevision.source_id == Source.id)
             .where(*_visible(owner_id, source_id, revision_id)).order_by(SourceDocument.id).limit(limit + 1))
    if after is not None:
        cursor = _uuid(after)
        cursor_exists = await session.scalar(
            select(SourceDocument.id)
            .join(SourceRevision, SourceDocument.revision_id == SourceRevision.id)
            .join(Source, SourceRevision.source_id == Source.id)
            .where(*_visible(owner_id, source_id, revision_id), SourceDocument.id == cursor)
        )
        if cursor_exists is None:
            raise LookupError("source unavailable")
        query = query.where(SourceDocument.id > cursor)
    ids = list((await session.execute(query)).scalars().all())
    if not ids:
        visible = await session.scalar(select(Source.id).join(SourceRevision, SourceRevision.source_id == Source.id)
                                       .where(*_visible(owner_id, source_id, revision_id)))
        if visible is None:
            raise LookupError("source unavailable")
    return DocumentPage(ids[:limit], ids[limit - 1] if len(ids) > limit else None)


async def read_document_range(
    session: AsyncSession, context: RuntimeContext, source_id: str, document_id: str, *, offset: int, limit: int,
) -> DocumentRange:
    if type(offset) is not int or type(limit) is not int or not 0 <= offset < 2**31 - 1 or not 1 <= limit <= 8000:
        raise ValueError("invalid document range")
    owner_id, source_id, revision_id = _scope(context, source_id)
    document_id = _uuid(document_id)
    query = (select(func.substr(SourceDocument.text, offset + 1, limit, type_=String()),
                    func.length(SourceDocument.text, type_=Integer()))
             .join(SourceRevision, SourceDocument.revision_id == SourceRevision.id)
             .join(Source, SourceRevision.source_id == Source.id)
             .where(*_visible(owner_id, source_id, revision_id), SourceDocument.id == document_id))
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise LookupError("source unavailable")
    content, length = row
    if offset > length:
        raise ValueError("invalid document range")
    return DocumentRange(source_id, revision_id, document_id, offset, offset + len(content), content)
