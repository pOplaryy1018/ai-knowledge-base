"""Explicit paid-provider smoke on synthetic data; embedding remains a declared fixture.

Run explicitly with pytest. Normal test discovery does not collect this file.
The integration fixture uses only the guarded isolated PostgreSQL database.
"""
import asyncio

import pytest

from app.core.config import settings
from app.services import wiki_service
from app.services.llm_service import stream_generate
from tests.integration.conftest import db_session, owner_kb  # noqa: F401
from tests.integration.test_wiki import wiki_client  # noqa: F401


@pytest.mark.asyncio
async def test_live_wiki_compile_publish_and_recompile(wiki_client, monkeypatch):  # noqa: F811
    if not settings.llm_api_key:
        pytest.skip("Live model is not configured")
    client, _, source, _ = wiki_client
    # wiki_client marks the provider synthetic. Restore only the real provider/key;
    # its deterministic 1024-dimensional query vector remains explicitly a fixture.
    from app.core.config import Settings
    configured = Settings()
    if not configured.llm_api_key:
        pytest.skip("Live model is not configured")
    monkeypatch.setattr(wiki_service.settings, "llm_api_key", configured.llm_api_key)
    monkeypatch.setattr(wiki_service, "stream_generate", stream_generate)
    response = await asyncio.wait_for(client.post("/api/wiki/pages", json={
        "title": "根据资料整理重试次数上限，不补充外部知识", "source_ids": [source.id],
    }), timeout=100)
    assert response.status_code == 201, f"Compile returned HTTP {response.status_code}"
    page = response.json()
    draft = page["draft_revision"]
    assert draft and draft["citations"] and "3" in draft["content"]
    assert all(not citation["unavailable"] for citation in draft["citations"])
    path = "/api/wiki/pages/" + page["id"]
    published = await client.post(path + "/publish", json={"expected_revision_id": draft["id"]})
    assert published.status_code == 200
    regenerated = await asyncio.wait_for(client.post(path + "/compile", json={
        "expected_revision_id": draft["id"], "source_ids": [source.id],
    }), timeout=100)
    assert regenerated.status_code == 200, f"Recompile returned HTTP {regenerated.status_code}"
    result = regenerated.json()
    assert result["published_revision"]["id"] == draft["id"]
    assert result["draft_revision"]["id"] != draft["id"]
    assert len(result["history"]) == 2
    print("Live LLM Wiki smoke passed: 2 real generations, cited draft, manual publish, preserved history. Embedding: deterministic fixture; OCR: not run.")
