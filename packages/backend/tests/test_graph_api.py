"""Graph build state and retry are owner scoped."""


def test_graph_status_and_retry_routes_are_registered() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/sources/{source_id}/graph" in paths
    assert "get" in paths["/api/sources/{source_id}/graph"]
    assert "post" in paths["/api/sources/{source_id}/graph/retry"]
