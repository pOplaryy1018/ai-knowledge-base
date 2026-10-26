"""Versioned Neo4j projection containing pointers, never source bodies."""

from dataclasses import dataclass

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import settings
from app.services.graph_extraction import ExtractedRelation, _normal_name

_driver: AsyncDriver | None = None


@dataclass(frozen=True)
class GraphCandidate:
    item_id: str
    source_id: str
    revision_id: str
    build_id: str
    route_rank: int


def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        if not settings.neo4j_uri or not settings.neo4j_password:
            raise RuntimeError("neo4j_unconfigured")
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=5, max_connection_pool_size=5,
        )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def setup_schema(driver: AsyncDriver | None = None) -> None:
    graph = driver or get_driver()
    for label, name in (("GraphRelation", "graph_relation_id"), ("GraphMention", "graph_mention_id")):
        await graph.execute_query(
            f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (node:{label}) REQUIRE node.id IS UNIQUE",
            database_="neo4j",
        )
    await graph.execute_query(
        "CREATE INDEX graph_relation_scope IF NOT EXISTS FOR (r:GraphRelation) "
        "ON (r.user_id, r.revision_id, r.build_id)", database_="neo4j")


async def write_projection(build_id: str, user_id: str, source_id: str, revision_id: str,
                           relations: list[ExtractedRelation], *, driver: AsyncDriver | None = None) -> None:
    graph = driver or get_driver()
    rows = []
    for relation in relations:
        rows.append({
            "id": f"{build_id}:{relation.id}", "subject_id": f"{build_id}:{relation.id}:s",
            "object_id": f"{build_id}:{relation.id}:o", "item_id": relation.item_id,
            "subject": relation.subject, "subject_type": relation.subject_type,
            "subject_norm": _normal_name(relation.subject),
            "subject_aliases": [_normal_name(alias) for alias in relation.subject_aliases],
            "object": relation.object, "object_type": relation.object_type,
            "object_norm": _normal_name(relation.object),
            "object_aliases": [_normal_name(alias) for alias in relation.object_aliases],
            "predicate": relation.predicate, "quote_start": relation.quote_start,
            "quote_end": relation.quote_end,
        })
    if not rows:
        return
    await graph.execute_query(
        """UNWIND $rows AS row
        MERGE (r:GraphRelation {id: row.id})
        SET r.build_id=$build_id, r.user_id=$user_id, r.source_id=$source_id,
            r.revision_id=$revision_id, r.item_id=row.item_id, r.predicate=row.predicate,
            r.quote_start=row.quote_start, r.quote_end=row.quote_end
        MERGE (s:GraphMention {id: row.subject_id})
        SET s.build_id=$build_id, s.name=row.subject, s.entity_type=row.subject_type,
            s.normalized_name=row.subject_norm, s.aliases=row.subject_aliases
        MERGE (o:GraphMention {id: row.object_id})
        SET o.build_id=$build_id, o.name=row.object, o.entity_type=row.object_type,
            o.normalized_name=row.object_norm, o.aliases=row.object_aliases
        MERGE (s)-[:SUBJECT_OF]->(r)
        MERGE (r)-[:OBJECT_OF]->(o)""",
        rows=rows, build_id=build_id, user_id=user_id, source_id=source_id,
        revision_id=revision_id, database_="neo4j",
    )


async def find_candidate_chunk_ids(user_id: str, revision_builds: dict[str, str],
                                   question: str, limit: int, *, driver: AsyncDriver | None = None) -> list[GraphCandidate]:
    if not revision_builds or not question.strip() or limit <= 0:
        return []
    graph = driver or get_driver()
    builds = [{"revision_id": revision, "build_id": build} for revision, build in revision_builds.items()]
    records, _, _ = await graph.execute_query(
        """UNWIND $builds AS build
        MATCH (r:GraphRelation {user_id: $user_id, revision_id: build.revision_id,
                                build_id: build.build_id})
        MATCH (mention:GraphMention)-[:SUBJECT_OF|OBJECT_OF]-(r)
        WHERE mention.normalized_name <> '' AND
          (toLower($question) CONTAINS mention.normalized_name OR
           any(alias IN mention.aliases WHERE alias <> '' AND toLower($question) CONTAINS alias))
        WITH r, count(DISTINCT mention) AS hits
        ORDER BY hits DESC, r.id
        RETURN DISTINCT r.item_id AS item_id, r.source_id AS source_id,
               r.revision_id AS revision_id, r.build_id AS build_id
        LIMIT $limit""",
        builds=builds, user_id=user_id, question=_normal_name(question), limit=min(limit, 50), database_="neo4j",
    )
    return [GraphCandidate(row["item_id"], row["source_id"], row["revision_id"], row["build_id"], rank)
            for rank, row in enumerate(records, 1)]


async def delete_build(build_id: str, *, driver: AsyncDriver | None = None) -> None:
    graph = driver or get_driver()
    await graph.execute_query("MATCH (node) WHERE node.build_id=$build_id DETACH DELETE node",
                              build_id=build_id, database_="neo4j")


async def delete_source(user_id: str, source_id: str, *, driver: AsyncDriver | None = None) -> None:
    graph = driver or get_driver()
    await graph.execute_query(
        """MATCH (r:GraphRelation {user_id:$user_id, source_id:$source_id})
        WITH collect(DISTINCT r.build_id) AS builds
        UNWIND builds AS build_id
        MATCH (node) WHERE node.build_id=build_id
        DETACH DELETE node""", user_id=user_id, source_id=source_id, database_="neo4j",
    )
