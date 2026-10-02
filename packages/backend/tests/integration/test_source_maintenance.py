"""Recovery must still run when the queue is down or busy tasks fill a batch."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.source import Source, SourceSyncTask
from app.services import source_cleanup, source_jobs


@pytest.fixture
async def maintenance(db_session, monkeypatch):
    @asynccontextmanager
    async def sessions():
        yield db_session

    monkeypatch.setattr(source_jobs, "async_session", sessions)
    impact = AsyncMock()
    cleanup = AsyncMock()
    monkeypatch.setattr(source_jobs, "process_impact_events", impact)
    monkeypatch.setattr(source_cleanup, "retry_source_cleanup", cleanup)
    return impact, cleanup


async def task(db_session, owner_kb, status, *, old=False):
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="recovery")
    db_session.add(source)
    await db_session.flush()
    row = SourceSyncTask(source_id=source.id, user_id=user.id, status=status)
    if old:
        row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    db_session.add(row)
    await db_session.flush()
    source.active_task_id = row.id
    await db_session.commit()
    return source, row


async def test_queue_outage_does_not_block_stale_recovery(db_session, owner_kb, maintenance):
    _, pending = await task(db_session, owner_kb, "pending")
    source, stale = await task(db_session, owner_kb, "processing", old=True)
    redis = AsyncMock()
    redis.enqueue_job.side_effect = ConnectionError("queue unavailable")
    await source_jobs.source_maintenance({"redis": redis})
    await db_session.refresh(stale)
    await db_session.refresh(source)
    assert stale.status == "failed"
    assert source.active_task_id is None
    assert pending.status == "pending"
    maintenance[0].assert_awaited_once()
    maintenance[1].assert_awaited_once()


async def test_busy_tasks_do_not_hide_recoverable_tasks(db_session, owner_kb, maintenance):
    for _ in range(100):
        await task(db_session, owner_kb, "processing")
    _, pending = await task(db_session, owner_kb, "pending")
    source, stale = await task(db_session, owner_kb, "processing", old=True)
    redis = AsyncMock()
    await source_jobs.source_maintenance({"redis": redis})
    await db_session.refresh(stale)
    await db_session.refresh(source)
    assert stale.status == "failed"
    assert source.active_task_id is None
    assert any(call.args[1] == pending.id for call in redis.enqueue_job.await_args_list)
