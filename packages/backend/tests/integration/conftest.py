"""Opt-in PostgreSQL tests: never use the application's database."""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL missing; PostgreSQL integration not verified")
    parsed = make_url(url)
    if parsed.database != "akb_evidence_test" or parsed.host not in {"localhost", "127.0.0.1"}:
        pytest.fail("Integration requires local dedicated akb_evidence_test database")
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
            yield session
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def owner_kb(db_session):
    from app.models.knowledge import KnowledgeBase
    from app.models.user import User

    user = User(username=__import__("uuid").uuid4().hex, hashed_password="test", role="user")
    db_session.add(user)
    await db_session.flush()
    kb = KnowledgeBase(name="Evidence test", user_id=user.id)
    db_session.add(kb)
    await db_session.flush()
    return user, kb


async def test_database_smoke(db_session):
    assert (await db_session.execute(text("SELECT 1"))).scalar_one() == 1
