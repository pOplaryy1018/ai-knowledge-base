# ruff: noqa: F811
import io

import pytest
from PIL import Image

from tests.integration.test_evidence_lifecycle import lifecycle_client  # noqa: F401, F811


async def test_image_empty_lifecycle(lifecycle_client, monkeypatch):
    from app.services import source_jobs
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    response = await client.post(
        "/api/sources",
        json={"name": "photo", "kind": "image", "config": {}, "knowledge_base_id": kb.id},
    )
    assert response.status_code == 201, response.text
    source_id = response.json()["id"]
    stream = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(stream, format="PNG")
    monkeypatch.setattr(image, "_default_ocr", lambda _: "")
    response = await client.post(
        f"/api/sources/{source_id}/image-revisions",
        files={"file": ("photo.png", stream.getvalue(), "image/png")},
    )
    assert response.status_code == 202, response.text
    task = response.json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    revision = (await client.get(f"/api/sources/{source_id}/revisions")).json()["items"][0]
    assert revision["manifest"]["needs_description"] is True
    assert revision["manifest"]["ocr_status"] == "no_text"
    original = await client.get(f"/api/sources/{source_id}/revisions/{revision['id']}/original")
    assert original.content == stream.getvalue()


async def create_image(client, kb):
    response = await client.post(
        "/api/sources",
        json={"name": "photo", "kind": "image", "config": {}, "knowledge_base_id": kb.id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def png(color="white"):
    stream = io.BytesIO()
    Image.new("RGB", (10, 10), color).save(stream, format="PNG")
    return stream.getvalue()


async def upload(client, source_id, data=None, **form):
    response = await client.post(
        f"/api/sources/{source_id}/image-revisions",
        files={"file": ("photo.png", data or png(), "image/png")},
        data=form,
    )
    return response


async def run_task(response):
    from app.services.source_jobs import process_source_import

    assert response.status_code == 202, response.text
    return await process_source_import({}, response.json()["task_id"])


async def head(client, source_id):
    return next(
        item
        for item in (await client.get("/api/sources")).json()["items"]
        if item["id"] == source_id
    )["current_revision_id"]


async def test_image_edits_replace_dedup_and_failure(lifecycle_client, monkeypatch, db_session):
    from unittest.mock import AsyncMock

    from app.models.source import SourceRevision, SourceSyncTask
    from app.services import source_jobs
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    source_id = await create_image(client, kb)
    calls = []
    monkeypatch.setattr(image, "_default_ocr", lambda _: calls.append(1) or "machine")
    first = await upload(client, source_id, manual_description="caption")
    assert (await run_task(first))["status"] == "completed"
    a = await head(client, source_id)
    revision_a = await db_session.get(SourceRevision, a)
    original = revision_a.file_path
    edit = await client.patch(
        f"/api/sources/{source_id}/image-text",
        json={
            "expected_revision_id": a,
            "manual_description": "changed",
            "ocr_correction": "fixed",
        },
    )
    assert (await run_task(edit))["status"] == "completed"
    b = await head(client, source_id)
    revision_b = await db_session.get(SourceRevision, b)
    assert revision_b.file_path == original and revision_b.manifest["ocr_text"] == "machine"
    assert len(calls) == 1
    back = await client.patch(
        f"/api/sources/{source_id}/image-text",
        json={"expected_revision_id": b, "manual_description": "caption", "ocr_correction": ""},
    )
    monkeypatch.setattr(
        source_jobs,
        "encode_texts",
        AsyncMock(side_effect=AssertionError("reuse must skip embedding")),
    )
    assert (await run_task(back))["status"] == "completed"
    assert await head(client, source_id) == a
    assert (await source_jobs.process_source_import({}, back.json()["task_id"]))[
        "status"
    ] == "completed"
    replacement = await upload(client, source_id, png("red"), expected_revision_id=a)
    assert (await run_task(replacement))["status"] == "failed"
    assert await head(client, source_id) == a
    task = await db_session.get(SourceSyncTask, replacement.json()["task_id"])
    assert task.payload["manual_description"] == "" and task.payload["ocr_correction"] == ""


async def test_image_validation_conflicts_and_redaction(lifecycle_client, monkeypatch, db_session):
    from app.models.source import SourceSyncTask
    from app.services import source_jobs
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    source_id = await create_image(client, kb)
    invalid = await upload(client, source_id, b"not a real png")
    assert invalid.status_code == 422
    oversized = await upload(client, source_id, b"0" * (image.MAX_IMAGE_BYTES + 1))
    assert oversized.status_code == 413
    monkeypatch.setattr(image, "_default_ocr", lambda _: "")
    first = await upload(client, source_id)
    assert (await upload(client, source_id)).status_code == 409
    assert (await run_task(first))["status"] == "completed"
    current = await head(client, source_id)
    assert (await upload(client, source_id)).status_code == 409
    queued = await upload(
        client, source_id, png("blue"), expected_revision_id=current, manual_description="private"
    )
    task = await db_session.get(SourceSyncTask, queued.json()["task_id"])
    path = task.payload["file_path"]
    assert (await client.delete(f"/api/sources/{source_id}")).status_code == 204
    await db_session.refresh(task)
    assert task.payload == {} and task.status == "failed"
    from sqlalchemy import select

    from app.models.asset_cleanup import AssetCleanup

    paths = (await db_session.execute(select(AssetCleanup.file_path))).scalars().all()
    assert path in paths
    assert (await source_jobs.process_source_import({}, task.id))["status"] == "cancelled"


async def test_image_unavailable_clear_and_reextract(lifecycle_client, monkeypatch, db_session):
    from app.models.source import SourceRevision
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    source_id = await create_image(client, kb)

    def unavailable(_):
        raise RuntimeError("ocr unavailable")

    monkeypatch.setattr(image, "_default_ocr", unavailable)
    assert (await run_task(await upload(client, source_id, manual_description="caption")))[
        "status"
    ] == "completed"
    a = await head(client, source_id)
    clear = await client.patch(
        f"/api/sources/{source_id}/image-text",
        json={"expected_revision_id": a, "manual_description": "", "ocr_correction": ""},
    )
    assert (await run_task(clear))["status"] == "completed"
    b = await head(client, source_id)
    revision = await db_session.get(SourceRevision, b)
    assert (
        revision.manifest["ocr_status"] == "unavailable"
        and revision.manifest["needs_description"] is True
    )
    monkeypatch.setattr(image, "_default_ocr", lambda _: "fresh OCR")
    result = await client.post(
        f"/api/sources/{source_id}/image-reextract", json={"expected_revision_id": b}
    )
    assert (await run_task(result))["status"] == "completed"
    revision = await db_session.get(SourceRevision, await head(client, source_id))
    assert (
        revision.manifest["ocr_text"] == "fresh OCR"
        and revision.manifest["manual_description"] == ""
    )


async def test_image_original_source_boundary(lifecycle_client, monkeypatch, db_session):
    from app.models.source import SourceRevision
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    monkeypatch.setattr(image, "_default_ocr", lambda _: "")
    a, b = await create_image(client, kb), await create_image(client, kb)
    assert (await run_task(await upload(client, a)))["status"] == "completed"
    assert (await run_task(await upload(client, b)))["status"] == "completed"
    ra = await db_session.get(SourceRevision, await head(client, a))
    rb = await db_session.get(SourceRevision, await head(client, b))
    ra.file_path = rb.file_path
    await db_session.commit()
    assert (await client.get(f"/api/sources/{a}/revisions/{ra.id}/original")).status_code == 404


async def test_image_stale_publication_blocked(lifecycle_client, monkeypatch, db_session):
    import numpy as np

    from app.models.source import Source
    from app.services import source_jobs
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    source_id = await create_image(client, kb)
    monkeypatch.setattr(image, "_default_ocr", lambda _: "ocr")
    assert (await run_task(await upload(client, source_id)))["status"] == "completed"
    first = await head(client, source_id)
    queued = await client.patch(
        f"/api/sources/{source_id}/image-text",
        json={"expected_revision_id": first, "manual_description": "changed"},
    )

    async def change_head(texts):
        source = await db_session.get(Source, source_id)
        source.current_revision_id = None
        await db_session.commit()
        return np.ones((len(texts), 1024))

    monkeypatch.setattr(source_jobs, "encode_texts", change_head)
    assert (await run_task(queued))["status"] == "failed"
    assert await head(client, source_id) is None


async def test_image_deleted_during_extraction(lifecycle_client, monkeypatch, db_session):
    import asyncio

    from app.models.source import SourceSyncTask
    from app.services import source_jobs
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    source_id = await create_image(client, kb)
    queued = await upload(client, source_id, manual_description="private")
    real = asyncio.to_thread

    async def delete_after_ocr(func, *args, **kwargs):
        result = await real(func, *args, **kwargs)
        if func is image.collect_image:
            assert (await client.delete(f"/api/sources/{source_id}")).status_code == 204
        return result

    monkeypatch.setattr(image, "_default_ocr", lambda _: "private OCR")
    monkeypatch.setattr(asyncio, "to_thread", delete_after_ocr)
    assert (await source_jobs.process_source_import({}, queued.json()["task_id"]))[
        "status"
    ] == "cancelled"
    task = await db_session.get(SourceSyncTask, queued.json()["task_id"])
    await db_session.refresh(task)
    assert task.payload == {} and task.revision_id is None


async def test_image_empty_skips_embeddings_and_blocks_foreign_owner(
    lifecycle_client, monkeypatch, db_session
):
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    from app.core.security import get_current_user
    from app.main import app
    from app.models.knowledge import KnowledgeItem
    from app.models.user import User
    from app.services import source_jobs
    from app.services.connectors import image

    client, user, kb = lifecycle_client
    source_id = await create_image(client, kb)
    monkeypatch.setattr(image, "_default_ocr", lambda _: "")
    embedding = AsyncMock(side_effect=AssertionError("empty images never embed"))
    monkeypatch.setattr(source_jobs, "encode_texts", embedding)
    assert (await run_task(await upload(client, source_id)))["status"] == "completed"
    embedding.assert_not_called()
    revision_id = await head(client, source_id)
    assert (
        not (
            await db_session.execute(
                select(KnowledgeItem.id).where(KnowledgeItem.revision_id == revision_id)
            )
        )
        .scalars()
        .all()
    )
    foreign = User(username="image-foreign", hashed_password="not-a-login-password")
    db_session.add(foreign)
    await db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: foreign
    assert (
        await client.get(f"/api/sources/{source_id}/revisions/{revision_id}/original")
    ).status_code == 404
    assert (await upload(client, source_id)).status_code == 404
    app.dependency_overrides[get_current_user] = lambda: user
    assert (await client.post(f"/api/sources/{source_id}/archive")).status_code == 200
    assert (await upload(client, source_id, expected_revision_id=revision_id)).status_code == 409


async def test_image_reextract_retains_caption_and_correction(
    lifecycle_client, monkeypatch, db_session
):
    from app.models.source import SourceRevision
    from app.services.connectors import image

    client, _, kb = lifecycle_client
    source_id = await create_image(client, kb)
    monkeypatch.setattr(image, "_default_ocr", lambda _: "old OCR")
    assert (await run_task(await upload(client, source_id, manual_description="keep caption")))[
        "status"
    ] == "completed"
    a = await head(client, source_id)
    edit = await client.patch(
        f"/api/sources/{source_id}/image-text",
        json={
            "expected_revision_id": a,
            "manual_description": "keep caption",
            "ocr_correction": "human corrected",
        },
    )
    assert (await run_task(edit))["status"] == "completed"
    b = await head(client, source_id)
    monkeypatch.setattr(image, "_default_ocr", lambda _: "fresh machine OCR")
    result = await client.post(
        f"/api/sources/{source_id}/image-reextract", json={"expected_revision_id": b}
    )
    assert (await run_task(result))["status"] == "completed"
    revision = await db_session.get(SourceRevision, await head(client, source_id))
    assert revision.manifest["ocr_text"] == "fresh machine OCR"
    assert revision.manifest["manual_description"] == "keep caption"
    assert revision.manifest["ocr_correction"] == "human corrected"


async def test_image_migration_downgrade_rejects_retained_inputs(
    lifecycle_client, monkeypatch, db_session
):
    import importlib.util
    from pathlib import Path

    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    client, _, kb = lifecycle_client
    source_id = await create_image(client, kb)
    assert (await upload(client, source_id)).status_code == 202
    spec = importlib.util.spec_from_file_location(
        "image_migration", Path("app/migrations/versions/20261002_image_tasks.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements = []
    monkeypatch.setattr(module.op, "execute", statements.append)
    monkeypatch.setattr(module.op, "drop_column", lambda *args: None)
    module.downgrade()
    with pytest.raises(DBAPIError, match="Image task inputs must be safely cleaned"):
        async with db_session.begin_nested():
            await db_session.execute(text(statements[0]))


@pytest.mark.parametrize("changed", ["archive", "active", "head"])
async def test_image_intake_refreshes_locked_source(
    lifecycle_client, monkeypatch, db_session, changed
):
    from datetime import datetime, timezone

    from sqlalchemy import update

    from app.api import source_api
    from app.models.source import Source

    client, user, kb = lifecycle_client
    source_id = await create_image(client, kb)
    from app.services.connectors import image

    monkeypatch.setattr(image, "_default_ocr", lambda _: "")
    assert (await run_task(await upload(client, source_id)))["status"] == "completed"
    expected = await head(client, source_id)
    original = source_api.owned_source
    count = 0

    async def concurrent_archive(session, source_id, user_id, *, lock=False):
        nonlocal count
        result = await original(session, source_id, user_id, lock=lock)
        if not lock:
            count += 1
            if count == 2:
                values = (
                    {"archived_at": datetime.now(timezone.utc)}
                    if changed == "archive"
                    else {"active_task_id": str(__import__("uuid").uuid4())}
                    if changed == "active"
                    else {"current_revision_id": None}
                )
                await session.execute(
                    update(Source)
                    .where(Source.id == source_id)
                    .values(**values)
                    .execution_options(synchronize_session=False)
                )
        return result

    monkeypatch.setattr(source_api, "owned_source", concurrent_archive)
    assert (await upload(client, source_id, expected_revision_id=expected)).status_code == 409
