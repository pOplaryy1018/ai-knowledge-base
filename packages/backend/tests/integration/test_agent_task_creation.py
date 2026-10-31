import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.agent_task import AgentTask
from app.models.source import Source, SourceRevision
from app.models.user import User
from app.services.agent_tasks import create_task, get_owned_task


async def test_create_is_idempotent_and_pins_snapshot(db_session, owner_kb):
    owner, kb = owner_kb
    source = Source(user_id=owner.id, knowledge_base_id=kb.id, name="synthetic")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid4().hex, pipeline_version="test", state="ready")
    db_session.add(revision)
    await db_session.flush()
    source.current_revision_id = revision.id
    await db_session.flush()

    first = await create_task(db_session, owner_id=owner.id, question="question", request_key="request-1")
    assert first.status == "queued" and first.source_versions == {source.id: revision.id}
    source.current_revision_id = None
    await db_session.flush()
    second = await create_task(db_session, owner_id=owner.id, question="question", request_key="request-1")
    assert second.id == first.id and second.source_versions == {source.id: revision.id}
    with pytest.raises(HTTPException) as conflict:
        await create_task(db_session, owner_id=owner.id, question="different", request_key="request-1")
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as foreign:
        await get_owned_task(db_session, first.id, str(uuid4()))
    assert foreign.value.status_code == 404
    assert (await get_owned_task(db_session, first.id, owner.id)).id == first.id


async def test_create_rejects_invalid_request_before_writing(db_session, owner_kb):
    owner, _ = owner_kb
    for question, key in [("", "valid"), ("   ", "valid"), ("x", ""), ("x", "a" * 201), ("q" * 20001, "ok")]:
        with pytest.raises(ValueError):
            await create_task(db_session, owner_id=owner.id, question=question, request_key=key)
    count = await db_session.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.owner_id == owner.id))
    assert count == 0


async def test_request_keys_are_isolated_per_user(db_session, owner_kb):
    owner, _ = owner_kb
    other = User(username=uuid4().hex, hashed_password="test", role="user")
    db_session.add(other)
    await db_session.flush()
    first = await create_task(db_session, owner_id=owner.id, question="q", request_key="same")
    second = await create_task(db_session, owner_id=other.id, question="q", request_key="same")
    assert first.id != second.id
    with pytest.raises(HTTPException) as error:
        await get_owned_task(db_session, second.id, owner.id)
    assert error.value.status_code == 404


async def test_concurrent_creation_is_atomic_on_separate_connections(db_session, monkeypatch):
    # db_session verifies the dedicated test database before a second engine is opened.
    del db_session
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = str(uuid4())
    from app.services import agent_tasks

    capture = agent_tasks.capture_source_versions
    reached = 0
    barrier = asyncio.Event()

    async def synchronized_capture(session, user_id):
        nonlocal reached
        versions = await capture(session, user_id)
        reached += 1
        if reached == 2:
            barrier.set()
        await barrier.wait()
        return versions

    monkeypatch.setattr(agent_tasks, "capture_source_versions", synchronized_capture)
    try:
        async with sessions.begin() as session:
            session.add(User(id=owner_id, username=uuid4().hex, hashed_password="test", role="user"))

        async def create_one(question="synthetic", key="same"):
            async with sessions.begin() as session:
                task = await create_task(session, owner_id=owner_id, question=question, request_key=key)
                return task.id

        first, second = await asyncio.wait_for(asyncio.gather(create_one(), create_one()), timeout=10)
        assert first == second
        async with sessions() as session:
            count = await session.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.owner_id == owner_id))
            assert count == 1
        reached = 0
        barrier = asyncio.Event()
        outcomes = await asyncio.wait_for(asyncio.gather(
            create_one("first", "conflict"), create_one("second", "conflict"), return_exceptions=True,
        ), timeout=10)
        assert sum(isinstance(item, str) for item in outcomes) == 1
        errors = [item for item in outcomes if isinstance(item, HTTPException)]
        assert len(errors) == 1 and errors[0].status_code == 409
        async with sessions() as session:
            count = await session.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.owner_id == owner_id))
            assert count == 2
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(AgentTask).where(AgentTask.owner_id == owner_id))
            await session.execute(delete(User).where(User.id == owner_id))
        await engine.dispose()
