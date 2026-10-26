"""Real isolated Neo4j driver tests for the derived relationship projection."""

import os
import uuid

import pytest
from neo4j import AsyncGraphDatabase

from app.services.graph_extraction import ExtractedRelation


@pytest.mark.asyncio
async def test_projection_is_idempotent_and_build_scoped() -> None:
    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        pytest.skip("TEST_NEO4J_URI missing; Neo4j integration not verified")
    assert uri in {"bolt://127.0.0.1:27687", "bolt://localhost:27687"}
    from app.services.graph_store import (
        delete_build,
        find_candidate_chunk_ids,
        setup_schema,
        write_projection,
    )

    user_id, source_id, revision_id, item_id, build_id = (str(uuid.uuid4()) for _ in range(5))
    relation = ExtractedRelation(
        id=str(uuid.uuid4()), item_id=item_id, subject="甲公司", subject_type="组织",
        predicate="收购", object="乙公司", object_type="组织", quote_start=0, quote_end=11,
    )
    async with AsyncGraphDatabase.driver(uri, auth=("neo4j", "evidence_test_only")) as driver:
        await setup_schema(driver)
        try:
            for _ in range(2):
                await write_projection(build_id, user_id, source_id, revision_id, [relation], driver=driver)
            found = await find_candidate_chunk_ids(user_id, {revision_id: build_id}, "甲公司收购了谁", 5, driver=driver)
            assert [row.item_id for row in found] == [item_id]
            assert await find_candidate_chunk_ids(str(uuid.uuid4()), {revision_id: build_id}, "甲公司", 5, driver=driver) == []
            assert await find_candidate_chunk_ids(user_id, {revision_id: str(uuid.uuid4())}, "甲公司", 5, driver=driver) == []
        finally:
            await delete_build(build_id, driver=driver)
