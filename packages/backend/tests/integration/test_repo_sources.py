import subprocess

import pytest

from tests.integration.test_evidence_lifecycle import lifecycle_client as lifecycle_client


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
async def test_local_repository_manual_sync_and_original(lifecycle_client, monkeypatch, tmp_path, object_format):
    from app.core.config import settings
    from app.services import source_jobs

    client, user, kb = lifecycle_client
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in [("init", f"--object-format={object_format}"), ("config", "user.name", "Test"), ("config", "user.email", "test@example.invalid")]:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / "policy.py").write_text("approval_days = 3\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "policy"], check=True, capture_output=True)
    monkeypatch.setattr(settings, "source_repo_roots", [{"id": "test", "label": "Test root", "path": str(tmp_path), "user_ids": [user.id]}])
    roots = await client.get("/api/source-repo-roots")
    assert roots.status_code == 200
    assert roots.json() == {"items": [{"id": "test", "label": "Test root"}]}
    created = await client.post("/api/sources", json={"name": "code", "knowledge_base_id": kb.id,
        "kind": "git_local", "config": {"root_id": "test", "relative_path": "repo"}})
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    task = await client.post(f"/api/sources/{source_id}/sync")
    assert task.status_code == 202, task.text
    assert (await source_jobs.process_source_import({}, task.json()["task_id"]))["status"] == "completed"
    versions = (await client.get(f"/api/sources/{source_id}/revisions")).json()["items"]
    assert len(versions) == 1 and len(versions[0]["commit"]) == (40 if object_format == "sha1" else 64)
    revision_id = versions[0]["id"]
    documents = (await client.get(f"/api/sources/{source_id}/revisions/{revision_id}/documents")).json()["items"]
    original = await client.get(f'/api/sources/{source_id}/revisions/{revision_id}/documents/{documents[0]["id"]}')
    assert original.json()["text"] == "approval_days = 3\n"
    archive = await client.get(f"/api/sources/{source_id}/revisions/{revision_id}/original")
    assert archive.status_code == 200
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(archive.content)) as contents:
        assert contents.read("policy.py") == b"approval_days = 3\n"
    (repo / "dirty-untracked.txt").write_text("not part of the commit")
    repeated = await client.post(f"/api/sources/{source_id}/sync")
    assert (await source_jobs.process_source_import({}, repeated.json()["task_id"]))["status"] == "completed"
    assert len((await client.get(f"/api/sources/{source_id}/revisions")).json()["items"]) == 1
    current = next(row for row in (await client.get("/api/sources")).json()["items"] if row["id"] == source_id)
    assert current["last_sync_manifest"]["dirty"] is True
    (repo / "dirty-untracked.txt").unlink()
    invalid_scope = await client.patch(f"/api/sources/{source_id}/scope", json={"include_paths": ["../outside"]})
    assert invalid_scope.status_code == 422
    for includes in [["policy.py"], []]:
        scoped = await client.patch(f"/api/sources/{source_id}/scope", json={"include_paths": includes})
        assert scoped.status_code == 200, scoped.text
        task = (await client.post(f"/api/sources/{source_id}/sync")).json()
        blocked = await client.patch(f"/api/sources/{source_id}/scope", json={"include_paths": []})
        assert blocked.status_code == 409
        assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    assert len((await client.get(f"/api/sources/{source_id}/revisions")).json()["items"]) == 2
    import json
    response = await client.post("/api/chat/scoped", json={"question": "approval days?", "source_ids": [source_id]})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    saved = await client.post("/api/answers", json={"message_id": events[-1]["message_id"]})
    assert saved.status_code == 201
    answer_id = saved.json()["id"]
    first_commit = versions[0]["commit"]
    (repo / "unrelated.txt").write_text("unrelated content\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "unrelated"], check=True, capture_output=True)
    task = (await client.post(f"/api/sources/{source_id}/sync")).json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    assert (await client.get(f"/api/answers/{answer_id}")).json()["status"] == "unchanged"
    # Delete the cited file while leaving an unrelated document in the snapshot.
    git_args = ["git", "-C", str(repo)]
    subprocess.run([*git_args, "rm", "policy.py"], check=True, capture_output=True)
    (repo / "remaining.txt").write_text("unrelated remaining text\n")
    subprocess.run([*git_args, "add", "."], check=True)
    subprocess.run([*git_args, "commit", "-m", "delete cited file"], check=True, capture_output=True)
    task = (await client.post(f"/api/sources/{source_id}/sync")).json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    missing = (await client.get(f"/api/answers/{answer_id}")).json()
    assert missing["evidence"][0]["state"] == "missing"
    (repo / "policy.py").write_text("approval_days = 5\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "changed"], check=True, capture_output=True)
    task = (await client.post(f"/api/sources/{source_id}/sync")).json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    assert (await client.get(f"/api/answers/{answer_id}")).json()["status"] == "needs_review"
    subprocess.run(["git", "-C", str(repo), "checkout", "--detach", first_commit], check=True, capture_output=True)
    task = (await client.post(f"/api/sources/{source_id}/sync")).json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    assert (await client.get(f"/api/answers/{answer_id}")).json()["status"] == "unchanged"


async def test_public_repository_uses_same_lifecycle(lifecycle_client, monkeypatch):
    from app.services import source_jobs
    from app.services.connectors import git_public
    from app.services.connectors.types import Snapshot
    from app.services.source_extraction import LocatedText

    client, _, kb = lifecycle_client
    snapshot_data = {"commit": "a" * 40, "text": "rule = 3"}
    monkeypatch.setattr(git_public, "collect_public", lambda *args, **kwargs: Snapshot(
        snapshot_data["commit"], [LocatedText("rule.py", snapshot_data["text"],
        {"commit": snapshot_data["commit"], "type": "git"})], {}, False, "test"))
    response = await client.post("/api/sources", json={"name": "public", "knowledge_base_id": kb.id,
        "kind": "git_public", "config": {"url": "https://github.com/octocat/Hello-World"}})
    assert response.status_code == 201, response.text
    source_id = response.json()["id"]
    task = (await client.post(f"/api/sources/{source_id}/sync")).json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    assert (await client.get(f"/api/sources/{source_id}/revisions")).json()["items"][0]["commit"] == "a" * 40
    import json
    chat = await client.post("/api/chat/scoped", json={"question": "rule?", "source_ids": [source_id]})
    events = [json.loads(line[6:]) for line in chat.text.splitlines() if line.startswith("data: ")]
    answer = (await client.post("/api/answers", json={"message_id": events[-1]["message_id"]})).json()
    snapshot_data.update(commit="b" * 40, text="rule = 5")
    task = (await client.post(f"/api/sources/{source_id}/sync")).json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "completed"
    assert (await client.get(f'/api/answers/{answer["id"]}')).json()["status"] == "needs_review"
    candidate = (await client.post(f'/api/answers/{answer["id"]}/candidates')).json()
    adopted = await client.post(f'/api/answers/{answer["id"]}/accept', json={"candidate_id": candidate["id"],
        "expected_answer_revision_id": candidate["expected_answer_revision_id"],
        "expected_source_versions": candidate["source_versions"]})
    assert adopted.status_code == 200 and len(adopted.json()["versions"]) == 2


async def test_local_source_denies_unassigned_root(lifecycle_client):
    client, _, kb = lifecycle_client
    response = await client.post("/api/sources", json={"name": "private", "knowledge_base_id": kb.id,
        "kind": "git_local", "config": {"root_id": "missing", "relative_path": "repo"}})
    assert response.status_code == 422


async def test_root_authorization_revoked_during_collection_prevents_publication(lifecycle_client, monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import source_jobs
    from app.services.connectors import git_local
    from app.services.connectors.types import Snapshot
    from app.services.source_extraction import LocatedText

    client, user, kb = lifecycle_client
    monkeypatch.setattr(settings, "source_repo_roots", [{"id": "test", "path": str(tmp_path), "user_ids": [user.id]}])
    response = await client.post("/api/sources", json={"name": "revoked", "knowledge_base_id": kb.id,
        "kind": "git_local", "config": {"root_id": "test", "relative_path": "."}})
    assert response.status_code == 201
    source_id = response.json()["id"]
    def collect(*args, **kwargs):
        settings.source_repo_roots = []
        return Snapshot("a" * 40, [LocatedText("rule.py", "rule = 3", {})], {}, False, "test")
    monkeypatch.setattr(git_local, "collect_local", collect)
    task = (await client.post(f"/api/sources/{source_id}/sync")).json()
    assert (await source_jobs.process_source_import({}, task["task_id"]))["status"] == "failed"
    rows = (await client.get("/api/sources")).json()["items"]
    assert next(row for row in rows if row["id"] == source_id)["current_revision_id"] is None
