import subprocess

import pytest

from app.services.connectors.git_snapshot import extract_snapshot
from app.services.connectors.types import SnapshotLimitError, SnapshotLimits
from tests.test_git_local import repo


def test_binary_and_submodule_are_skipped(tmp_path):
    path = repo(tmp_path)
    (path / "image.bin").write_bytes(b"a\x00b")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "binary"], check=True, capture_output=True
    )
    snap = extract_snapshot(path)
    assert any(item["reason"] == "binary" for item in snap.manifest["skipped"])
    assert snap.manifest["complete"]
    assert snap.documents[0].locator["path"] == "a.py"


def test_config_scope_changes_fingerprint(tmp_path):
    path = repo(tmp_path)
    assert (
        extract_snapshot(path).config_fingerprint
        != extract_snapshot(path, include_paths=("a.py",)).config_fingerprint
    )


def test_file_count_limit(tmp_path):
    path = repo(tmp_path)
    with pytest.raises(SnapshotLimitError):
        extract_snapshot(path, limits=SnapshotLimits(max_files=0))


def test_fetch_storage_budget_uses_real_git(tmp_path):
    from app.services.connectors.git_snapshot import run_git

    with pytest.raises(SnapshotLimitError):
        run_git(tmp_path, ["init", "--bare", "."], storage_budget=1)


def test_reduced_scope_can_fit_file_budget(tmp_path):
    path = repo(tmp_path)
    (path / "b.py").write_text("second")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "second"], check=True, capture_output=True
    )
    snap = extract_snapshot(path, limits=SnapshotLimits(max_files=1), include_paths=("a.py",))
    assert len(snap.documents) == 1
