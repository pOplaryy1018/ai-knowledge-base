"""Dedicated PostgreSQL Wiki ownership, revision and publication lifecycle."""
import importlib.util
from contextlib import asynccontextmanager
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import select

from app.core.security import get_current_user
from app.main import app
from app.models.source import Source, SourceRevision
from app.services.source_extraction import LocatedText
from app.services.source_publication import publish_revision, store_revision_documents


@pytest.fixture
async def wiki_client(db_session, owner_kb, monkeypatch, client):
    from app.api import wiki_api
    from app.services import scoped_chat_service, search_service, wiki_service
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Original")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash="wiki-first", pipeline_version="test")
    db_session.add(revision)
    await db_session.flush()
    await store_revision_documents(db_session, source, revision,
                                   [LocatedText("text", "Retry attempts are limited to 3.", {"type": "text"})],
                                   [[1.0] * 1024])
    await publish_revision(db_session, source.id, revision.id, None)
    await db_session.commit()
    @asynccontextmanager
    async def sessions():
        yield db_session
    for module in (wiki_api, scoped_chat_service, search_service):
        monkeypatch.setattr(module, "async_session", sessions)
    async def encode(texts):
        return np.ones(1024)
    async def provider(*args, **kwargs):
        yield "Retry attempts are limited to 3. [1]"
    monkeypatch.setattr(search_service, "encode_texts", encode)
    monkeypatch.setattr(wiki_service, "stream_generate", provider)
    monkeypatch.setattr(wiki_service.settings, "llm_api_key", "synthetic-test-key")
    app.dependency_overrides[get_current_user] = lambda: user
    yield client, user, source, revision
    app.dependency_overrides.pop(get_current_user, None)


async def create_page(client, source, title="Retry rules"):
    response = await client.post("/api/wiki/pages", json={"title": title, "source_ids": [source.id]})
    assert response.status_code == 201, response.text
    return response.json()


async def test_draft_edit_publish_history_and_export(wiki_client):
    client, _, source, _ = wiki_client
    page = await create_page(client, source)
    path = "/api/wiki/pages/" + page["id"]
    first = page["draft_revision"]["id"]
    assert page["published_revision"] is None and len(page["history"]) == 1
    assert (await client.get(path + "/export")).status_code == 422
    edited = await client.patch(path + "/draft", json={"expected_revision_id": first, "title": "Retry policy",
                                                       "content": "At most 3 attempts. [1]"})
    assert edited.status_code == 200, edited.text
    second = edited.json()["draft_revision"]["id"]
    assert second != first and len(edited.json()["history"]) == 2
    assert (await client.post(path + "/publish", json={"expected_revision_id": first})).status_code == 409
    published = await client.post(path + "/publish", json={"expected_revision_id": second})
    assert published.status_code == 200, published.text
    assert published.json()["draft_revision"] is None
    assert published.json()["published_revision"]["id"] == second
    exported = await client.get(path + "/export")
    assert exported.status_code == 200
    assert "text/markdown" in exported.headers["content-type"]
    assert "attachment" in exported.headers["content-disposition"]
    assert source.id in exported.text and "At most 3 attempts" in exported.text
    compiled = await client.post(path + "/compile", json={"expected_revision_id": second, "source_ids": [source.id]})
    assert compiled.status_code == 200, compiled.text
    assert compiled.json()["published_revision"]["id"] == second
    assert compiled.json()["draft_revision"]["id"] not in {first, second}
    assert len(compiled.json()["history"]) == 3
    assert (await client.get("/api/wiki/pages", params={"q": "Retry policy"})).json()["items"]


async def test_unknown_reference_stale_edits_and_foreign_ownership(wiki_client):
    from app.models.user import User
    client, user, source, _ = wiki_client
    page = await create_page(client, source)
    path = "/api/wiki/pages/" + page["id"]
    revision_id = page["draft_revision"]["id"]
    invalid = await client.patch(path + "/draft", json={"expected_revision_id": revision_id, "title": "Retry", "content": "Invented[99]"})
    assert invalid.status_code == 422
    edited = await client.patch(path + "/draft", json={"expected_revision_id": revision_id, "title": "Retry", "content": "Still 3.[1]"})
    assert edited.status_code == 200
    assert (await client.post(path + "/compile", json={"expected_revision_id": revision_id, "source_ids": [source.id]})).status_code == 409
    app.dependency_overrides[get_current_user] = lambda: User(id=str(uuid4()), username="foreign", role="user")
    for method, suffix, body in [("GET", "", None), ("GET", "/export", None),
                                  ("PATCH", "/draft", {"expected_revision_id": revision_id, "title": "x", "content": "x[1]"}),
                                  ("POST", "/publish", {"expected_revision_id": revision_id}),
                                  ("POST", "/compile", {"expected_revision_id": revision_id, "source_ids": [source.id]})]:
        response = await client.request(method, path + suffix, **({"json": body} if body else {}))
        assert response.status_code == 404, response.text
    assert (await client.get("/api/wiki/pages")).json()["items"] == []
    app.dependency_overrides[get_current_user] = lambda: user


async def test_source_change_blocks_publish_and_deleted_evidence_is_unavailable(wiki_client, db_session):
    from app.services.source_cleanup import redact_source
    client, _, source, old = wiki_client
    page = await create_page(client, source)
    path = "/api/wiki/pages/" + page["id"]
    new = SourceRevision(source_id=source.id, raw_hash="wiki-second", pipeline_version="test", state="ready")
    db_session.add(new)
    await db_session.flush()
    await publish_revision(db_session, source.id, new.id, old.id)
    await db_session.commit()
    assert (await client.get(path)).json()["source_changed"] is True
    assert (await client.post(path + "/publish", json={"expected_revision_id": page["draft_revision"]["id"]})).status_code == 409
    await redact_source(db_session, source.id)
    await db_session.commit()
    detail = (await client.get(path)).json()
    for revision in detail["history"]:
        assert all(c["unavailable"] and c["content"] is None and c["quote"] is None for c in revision["citations"])


async def test_existing_owned_wikilinks_and_published_backlinks(wiki_client):
    client, _, source, _ = wiki_client
    target = await create_page(client, source, "Target")
    origin = await create_page(client, source, "Origin")
    path = "/api/wiki/pages/" + origin["id"]
    response = await client.patch(path + "/draft", json={"expected_revision_id": origin["draft_revision"]["id"],
        "title": "Origin", "content": "Fact[1] [[" + target["slug"] + "]] [[does-not-exist]]"})
    assert response.status_code == 200, response.text
    assert [link["id"] for link in response.json()["links"]] == [target["id"]]
    assert (await client.get("/api/wiki/pages/" + target["id"])).json()["backlinks"] == []
    response = await client.post(path + "/publish", json={"expected_revision_id": response.json()["draft_revision"]["id"]})
    assert response.status_code == 200
    assert [link["id"] for link in (await client.get("/api/wiki/pages/" + target["id"])).json()["backlinks"]] == [origin["id"]]


async def test_compile_rechecks_the_head_after_external_generation(wiki_client, monkeypatch, db_session):
    from app.services import wiki_service
    client, _, source, _ = wiki_client
    page = await create_page(client, source)
    original = page["draft_revision"]["id"]
    async def provider(*args, **kwargs):
        source.current_revision_id = None
        await db_session.commit()
        yield "Fact[1]"
    monkeypatch.setattr(wiki_service, "stream_generate", provider)
    path = "/api/wiki/pages/" + page["id"]
    result = await client.post(path + "/compile", json={"expected_revision_id": original, "source_ids": [source.id]})
    assert result.status_code == 409
    detail = (await client.get(path)).json()
    assert detail["draft_revision"]["id"] == original and len(detail["history"]) == 1


async def test_generation_directory_does_not_include_another_users_pages(wiki_client, monkeypatch, db_session):
    from app.models.user import User
    from app.models.wiki import WikiPage, WikiRevision
    from app.services import wiki_service
    client, _, source, _ = wiki_client
    owned = await create_page(client, source, "Owned topic")
    foreign = User(username=uuid4().hex, hashed_password="test", role="user")
    db_session.add(foreign)
    await db_session.flush()
    page = WikiPage(user_id=foreign.id, slug="private-foreign-slug")
    db_session.add(page)
    await db_session.flush()
    revision = WikiRevision(page_id=page.id, title="Private foreign title", content="private", source_versions={}, citations=[])
    db_session.add(revision)
    await db_session.flush()
    page.draft_revision_id = revision.id
    await db_session.commit()
    seen = []
    async def provider(prompt, *args, **kwargs):
        seen.append(prompt)
        yield "Fact[1]"
    monkeypatch.setattr(wiki_service, "stream_generate", provider)
    await create_page(client, source, "Next topic")
    assert owned["slug"] in seen[0]
    assert "private-foreign-slug" not in seen[0] and "Private foreign title" not in seen[0]


async def test_missing_llm_does_not_create_a_page(wiki_client, monkeypatch, db_session):
    from app.models.wiki import WikiPage
    from app.services import wiki_service
    client, _, source, _ = wiki_client
    monkeypatch.setattr(wiki_service.settings, "llm_api_key", "")
    response = await client.post("/api/wiki/pages", json={"title": "Topic", "source_ids": [source.id]})
    assert response.status_code == 503
    assert not (await db_session.execute(select(WikiPage))).scalars().all()


async def test_wiki_downgrade_refuses_existing_pages(wiki_client, db_session):
    from pathlib import Path
    from unittest.mock import patch

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import DBAPIError
    client, _, source, _ = wiki_client
    await create_page(client, source)
    path = Path(__file__).parents[2] / "app/migrations/versions/20261014_wiki.py"
    spec = importlib.util.spec_from_file_location("wiki_pg_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def downgrade(sync_session):
        with patch.object(migration, "op", Operations(MigrationContext.configure(sync_session.connection()))):
            migration.downgrade()
    with pytest.raises(DBAPIError, match="Wiki history"):
        async with db_session.begin_nested():
            await db_session.run_sync(downgrade)
    from app.models.wiki import WikiPage
    assert (await db_session.execute(select(WikiPage))).scalars().all()
