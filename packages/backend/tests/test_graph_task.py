"""Graph build state is durable and unique per immutable source revision."""

import importlib
import importlib.util

from sqlalchemy import UniqueConstraint


def test_graph_build_task_has_unique_revision_and_extractor() -> None:
    assert importlib.util.find_spec("app.models.graph_task") is not None
    graph_task = importlib.import_module("app.models.graph_task")
    table = graph_task.GraphBuildTask.__table__
    assert {column.name for column in table.columns} >= {
        "source_id", "revision_id", "user_id", "extractor_version", "status",
        "active_build_id", "lease_until", "attempts", "relation_count", "rejected_count", "error_code",
    }
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"revision_id", "extractor_version"}
        for constraint in table.constraints
    )


def test_graph_cleanup_survives_source_row_deletion() -> None:
    graph_task = importlib.import_module("app.models.graph_task")
    table = graph_task.GraphCleanup.__table__
    assert {column.name for column in table.columns} >= {"source_id", "user_id", "status"}
    assert not table.foreign_keys
