"""Authenticated Wiki drafts, manual publication and Markdown export."""
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.wiki import WikiPage, WikiRevision
from app.schemas.wiki import WikiCompile, WikiCreate, WikiEdit, WikiExpected
from app.services import wiki_service as service
from app.services.scoped_chat_service import resolve_scope

router = APIRouter(prefix="/wiki", tags=["LLM Wiki"])


async def lock_owner(session: AsyncSession, user_id: str) -> None:
    owner = (await session.execute(select(User).where(User.id == user_id)
                                    .with_for_update())).scalar_one_or_none()
    if owner is None:
        raise HTTPException(404, "用户不存在")


@router.get("/pages")
async def pages(q: str = Query(default="", max_length=200), user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        rows = (await session.execute(select(WikiPage).where(WikiPage.user_id == user.id)
                                      .order_by(WikiPage.updated_at.desc(), WikiPage.id))).scalars().all()
        items = []
        for page in rows:
            active_id = page.draft_revision_id or page.published_revision_id
            active = await session.get(WikiRevision, active_id) if active_id else None
            if q.strip() and (active is None or q.strip().casefold() not in
                              (active.title + "\n" + active.content + "\n" + page.slug).casefold()):
                continue
            items.append(await service.page_summary(session, page))
        return {"items": items}


@router.post("/pages", status_code=201)
async def create(body: WikiCreate, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        versions = await resolve_scope(session, user.id, [str(value) for value in body.source_ids])
        directory = await service.wiki_directory(session, user.id)
    content, citations = await service.generate_wiki(body.title, versions, user.id, directory=directory)
    async with async_session() as session:
        await lock_owner(session, user.id)
        if not await service.check_sources(session, versions, user.id, lock=True):
            raise HTTPException(409, service.STALE_SOURCE)
        page = WikiPage(user_id=user.id, slug=await service.new_slug(session, user.id, body.title))
        session.add(page)
        await session.flush()
        await service.append_revision(session, page, body.title, content, versions, citations, kind="generated")
        await session.commit()
        return await service.page_detail(session, page)


@router.get("/pages/{page_id}")
async def detail(page_id: UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        return await service.page_detail(session, await service.owned_page(session, str(page_id), user.id))


@router.patch("/pages/{page_id}/draft")
async def edit(page_id: UUID, body: WikiEdit, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        # Verify ownership before looking up or mutating any revision.
        await service.owned_page(session, str(page_id), user.id)
        await lock_owner(session, user.id)
        page = await service.owned_page(session, str(page_id), user.id, lock=True)
        service.check_expected(page, str(body.expected_revision_id))
        previous = await session.get(WikiRevision, str(body.expected_revision_id))
        if previous is None or previous.page_id != page.id:
            raise HTTPException(409, service.STALE_WIKI)
        citations = await service.materialize_citations(session, previous, user.id)
        await service.append_revision(session, page, body.title, body.content, previous.source_versions, citations, kind="edited")
        await session.commit()
        return await service.page_detail(session, page)


@router.post("/pages/{page_id}/compile")
async def compile_draft(page_id: UUID, body: WikiCompile, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        page = await service.owned_page(session, str(page_id), user.id)
        service.check_expected(page, str(body.expected_revision_id))
        previous = await session.get(WikiRevision, str(body.expected_revision_id))
        if previous is None or previous.page_id != page.id:
            raise HTTPException(409, service.STALE_WIKI)
        title = previous.title
        versions = await resolve_scope(session, user.id, [str(value) for value in body.source_ids])
        directory = await service.wiki_directory(session, user.id)
    content, citations = await service.generate_wiki(title, versions, user.id, directory=directory)
    async with async_session() as session:
        await lock_owner(session, user.id)
        if not await service.check_sources(session, versions, user.id, lock=True):
            raise HTTPException(409, service.STALE_SOURCE)
        page = await service.owned_page(session, str(page_id), user.id, lock=True)
        service.check_expected(page, str(body.expected_revision_id))
        await service.append_revision(session, page, title, content, versions, citations, kind="generated")
        await session.commit()
        return await service.page_detail(session, page)


@router.post("/pages/{page_id}/publish")
async def publish(page_id: UUID, body: WikiExpected, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        page = await service.owned_page(session, str(page_id), user.id)
        service.check_expected(page, str(body.expected_revision_id))
        revision = await session.get(WikiRevision, str(body.expected_revision_id))
        if revision is None or revision.page_id != page.id:
            raise HTTPException(409, service.STALE_WIKI)
        await lock_owner(session, user.id)
        if not await service.check_sources(session, revision.source_versions, user.id, lock=True):
            raise HTTPException(409, service.STALE_SOURCE)
        page = await service.owned_page(session, str(page_id), user.id, lock=True)
        service.check_expected(page, str(body.expected_revision_id))
        if page.draft_revision_id != revision.id:
            raise HTTPException(409, service.STALE_WIKI)
        citations = await service.materialize_citations(session, revision, user.id)
        try:
            service.validate_wiki_content(revision.content, citations)
        except ValueError as error:
            raise HTTPException(409, "原文引用已不可用，请重新编译并复核草稿") from error
        if any(citation["unavailable"] for citation in citations):
            raise HTTPException(409, "原文引用已不可用，请重新编译并复核草稿")
        page.published_revision_id, page.draft_revision_id = revision.id, None
        page.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return await service.page_detail(session, page)


@router.get("/pages/{page_id}/export")
async def export(page_id: UUID, user: User = Depends(get_current_user)) -> Response:
    async with async_session() as session:
        page = await service.owned_page(session, str(page_id), user.id)
        markdown = await service.export_markdown(session, page)
        return Response(markdown, media_type="text/markdown", headers={
            "Content-Disposition": f'attachment; filename="wiki-{page.id}.md"; filename*=UTF-8\'\'wiki-{quote(page.slug)}.md',
        })
