import subprocess

import pytest

from app.services.connectors.git_local import collect_local
from app.services.connectors.types import ConnectorError, SnapshotLimitError, SnapshotLimits


def repo(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.org"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "core.autocrlf", "false"], check=True)
    (tmp_path / "a.py").write_bytes(b"def f():\r\n    return 1\r\n")
    (tmp_path / ".env").write_text("secret")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "first"], check=True, capture_output=True
    )
    return tmp_path


def test_committed_raw_text_and_dirty(tmp_path):
    path = repo(tmp_path)
    (path / "a.py").write_text("changed")
    (path / "new.py").write_text("untracked")
    snap = collect_local(path, allowed_roots=[tmp_path], authorized=True)
    assert snap.dirty
    assert len(snap.documents) == 1
    assert snap.documents[0].text == "def f():\r\n    return 1\r\n"
    assert snap.documents[0].locator["commit"] == snap.commit
    assert snap.manifest["skipped"][0]["reason"] == "sensitive"


def test_authorization_and_limits(tmp_path):
    path = repo(tmp_path)
    with pytest.raises(ConnectorError):
        collect_local(path, allowed_roots=[tmp_path], authorized=False)
    with pytest.raises(ConnectorError):
        collect_local(path, allowed_roots=[tmp_path / "other"], authorized=True)
    with pytest.raises(SnapshotLimitError):
        collect_local(
            path, allowed_roots=[tmp_path], authorized=True, limits=SnapshotLimits(max_file_bytes=2)
        )


def test_alternates_rejected(tmp_path):
    path = repo(tmp_path)
    (path / ".git/objects/info/alternates").write_text(str(tmp_path.parent))
    with pytest.raises(ConnectorError):
        collect_local(path, allowed_roots=[tmp_path], authorized=True)


def test_symbolic_repo_rejected(tmp_path):
    target = repo(tmp_path / "target")
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symbolic links unavailable")
    with pytest.raises(ConnectorError):
        collect_local(link, allowed_roots=[tmp_path], authorized=True)


def test_filters_are_refused_before_status(tmp_path):
    path = repo(tmp_path)
    subprocess.run(
        ["git", "-C", str(path), "config", "filter.evil.clean", "echo unsafe"], check=True
    )
    with pytest.raises(ConnectorError):
        collect_local(path, allowed_roots=[tmp_path], authorized=True)


def test_git_directory_junction_rejected(tmp_path):
    target = repo(tmp_path / "target")
    holder = tmp_path / "holder"
    holder.mkdir()
    command = (
        "New-Item -ItemType Junction -Path '"
        + str(holder / ".git")
        + "' -Target '"
        + str(target / ".git")
        + "'"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True)
    if result.returncode:
        pytest.skip("Junction unavailable")
    with pytest.raises(ConnectorError):
        collect_local(holder, allowed_roots=[holder], authorized=True)
