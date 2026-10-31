import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import pytest

from app.services.asset_storage import (
    StageCommittedCleanupError,
    recover_orphan_stages,
    resolve_asset_path,
    stage_asset,
)


@pytest.mark.parametrize("relative", ["../outside.txt", "", ".", "owner/../../outside.txt"])
def test_asset_path_rejects_parent_escape_or_root(tmp_path: Path, relative: str) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_asset_path(root, relative)


def test_asset_path_rejects_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_asset_path(root, str(tmp_path / "outside.txt"))


def test_asset_path_accepts_child(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    assert resolve_asset_path(root, "owner/source/revision.bin") == (
        root / "owner" / "source" / "revision.bin"
    ).resolve()


def test_asset_path_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {type(exc).__name__}")
    with pytest.raises(ValueError):
        resolve_asset_path(root, "link/revision.bin")


def test_failed_stage_does_not_overwrite_original(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    original = root / "version.bin"
    original.write_bytes(b"original")

    class BrokenStream(BytesIO):
        def read(self, size: int = -1) -> bytes:
            raise OSError("synthetic read failure")

    with pytest.raises(OSError):
        stage_asset(root, "version.bin", BrokenStream(b"new"))
    assert original.read_bytes() == b"original"
    assert sorted(p.name for p in root.iterdir()) == [".asset-staging", "version.bin"]
    assert list((root / ".asset-staging").iterdir()) == []


def test_validation_failure_cleans_only_temporary_file(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    existing = root / "keep.bin"
    existing.write_bytes(b"keep")

    def reject(_path: Path) -> None:
        raise ValueError("invalid asset")

    with pytest.raises(ValueError):
        stage_asset(root, "new.bin", BytesIO(b"new"), validate=reject)
    assert existing.read_bytes() == b"keep"
    assert sorted(path.name for path in root.iterdir()) == [".asset-staging", "keep.bin"]
    assert list((root / ".asset-staging").iterdir()) == []


def test_stage_and_concurrent_duplicate_never_replace_version(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()

    def write(data: bytes) -> str:
        try:
            stage_asset(root, "owner/version.bin", BytesIO(data))
            return "created"
        except FileExistsError:
            return "exists"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [b"first", b"second"]))
    assert sorted(results) == ["created", "exists"]
    assert (root / "owner/version.bin").read_bytes() in {b"first", b"second"}
    assert sorted(path.name for path in root.iterdir()) == [".asset-staging", "owner"]
    assert list((root / ".asset-staging").iterdir()) == []


@pytest.mark.parametrize("relative", [".asset-staging/file", ".ASSET-STAGING/file", ".asset-staging./file"])
def test_staging_namespace_is_never_a_destination(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError):
        resolve_asset_path(tmp_path, relative)


def test_committed_cleanup_failure_reports_committed_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_unlink = Path.unlink

    def fail_staged(path: Path, *args: object, **kwargs: object) -> None:
        if path.parent.name == ".asset-staging":
            raise PermissionError("synthetic failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_staged)
    with pytest.raises(StageCommittedCleanupError) as error:
        stage_asset(tmp_path, "version.bin", BytesIO(b"synthetic"))
    assert error.value.target == tmp_path / "version.bin"
    assert error.value.target.read_bytes() == b"synthetic"
    assert len(list((tmp_path / ".asset-staging").iterdir())) == 1


def test_recovery_requires_paused_writers_and_preserves_non_staging_files(tmp_path: Path) -> None:
    staging = tmp_path / ".asset-staging"
    staging.mkdir()
    orphan = staging / ".asset-stage-12345678"
    orphan.write_bytes(b"temporary")
    other = staging / "unrelated"
    other.write_bytes(b"untouched")
    old = tmp_path / ".asset-stage-12345678"
    old.write_bytes(b"legacy")
    with pytest.raises(ValueError):
        recover_orphan_stages(tmp_path, writers_paused=False)
    assert orphan.exists()
    assert recover_orphan_stages(tmp_path, writers_paused=True) == 1
    assert not orphan.exists()
    assert other.read_bytes() == b"untouched"
    assert old.read_bytes() == b"legacy"


def test_recovery_does_not_follow_stage_symlink(tmp_path: Path) -> None:
    staging = tmp_path / ".asset-staging"
    staging.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"safe")
    try:
        (staging / ".asset-stage-12345678").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {type(exc).__name__}")
    assert recover_orphan_stages(tmp_path, writers_paused=True) == 0
    assert outside.read_bytes() == b"safe"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction coverage")
def test_recovery_rejects_junction_staging_directory(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", os.fspath(root / ".asset-staging"), os.fspath(outside)],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        pytest.skip("junction creation unavailable")
    with pytest.raises(ValueError):
        recover_orphan_stages(root, writers_paused=True)


def test_linked_stage_left_by_crash_can_be_recovered(tmp_path: Path) -> None:
    script = """
import os, sys
from io import BytesIO
from pathlib import Path
from app.services.asset_storage import stage_asset
link = os.link
def crash(source, target):
    link(source, target)
    os._exit(0)
os.link = crash
stage_asset(Path(sys.argv[1]), 'version.bin', BytesIO(b'synthetic'))
"""
    proc = subprocess.run([sys.executable, "-c", script, os.fspath(tmp_path)], check=False)
    assert proc.returncode == 0
    assert (tmp_path / "version.bin").read_bytes() == b"synthetic"
    assert len(list((tmp_path / ".asset-staging").iterdir())) == 1
    assert recover_orphan_stages(tmp_path, writers_paused=True) == 1
    assert (tmp_path / "version.bin").read_bytes() == b"synthetic"
