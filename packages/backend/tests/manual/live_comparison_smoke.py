"""Explicit live-provider smoke test on synthetic sources in the isolated DB.
Run this file explicitly; it is excluded from normal test discovery.
"""
import asyncio

import pytest

from app.core.config import settings
from app.services import comparison_service
from app.services.llm_service import stream_generate
from tests.integration.conftest import db_session, owner_kb  # noqa: F401
from tests.integration.test_comparison import comparison_scope  # noqa: F401


@pytest.mark.asyncio
async def test_live_comparison_synthetic_sources(comparison_scope, monkeypatch):  # noqa: F811
    if not settings.llm_api_key:
        pytest.skip("Live model is not configured")
    user, versions = comparison_scope
    monkeypatch.setattr(comparison_service, "stream_generate", stream_generate)
    content, citations, artifact, warning = await asyncio.wait_for(
        comparison_service.generate_comparison(
            "请按事务支持、索引结构两个维度比较这些资料。逐份使用该资料自己的证据编号，无依据明确标注。",
            versions, user.id,
        ), timeout=75,
    )
    assert artifact is not None and warning is None, warning
    assert len(artifact["sources"]) == 2
    assert len(artifact["rows"]) == 2
    assert {entry["source_id"] for entry in citations} == set(versions)
    assert "未找到依据" not in content
    print(f"Live model comparison passed: {len(artifact['rows'])} dimensions, {len(citations)} immutable citations")
