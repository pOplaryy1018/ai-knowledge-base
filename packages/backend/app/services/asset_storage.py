"""Stage immutable asset bytes inside a service-controlled storage root.

The storage root and its directories must not be writable by untrusted users.
Paths are validated here; caller authorization and publication are separate.
"""

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

_STAGING_DIR = ".asset-staging"
_STAGING_PREFIX = ".asset-stage-"


class StageCommittedCleanupError(OSError):
    """The immutable target was linked, but its temporary link needs recovery."""

    def __init__(self, target: Path) -> None:
        super().__init__("asset committed; temporary cleanup is pending")
        self.target = target


def _staging_directory(root: Path, *, create: bool) -> Path | None:
    staging = root / _STAGING_DIR
    if create:
        staging.mkdir(exist_ok=True)
    if staging.is_symlink() or staging.is_junction():
        raise ValueError("staging directory cannot be a link")
    if not staging.exists():
        return None
    if not staging.is_dir() or staging.resolve().parent != root:
        raise ValueError("invalid staging directory")
    return staging


def recover_orphan_stages(root: Path, *, writers_paused: bool) -> int:
    """Recover abandoned staging links while an external global write gate is held.

    The caller must ensure all processes sharing this storage are stopped or
    excluded for the entire scan. The flag is an assertion of that precondition,
    not a lock or an online lease mechanism.
    """
    if writers_paused is not True:
        raise ValueError("all writers must be paused during recovery")
    storage_root = root.resolve(strict=True)
    staging = _staging_directory(storage_root, create=False)
    if staging is None:
        return 0
    count = 0
    with os.scandir(staging) as entries:
        for entry in entries:
            if entry.name.startswith(_STAGING_PREFIX) and entry.is_file(follow_symlinks=False):
                os.unlink(entry.path)
                count += 1
    return count


def resolve_asset_path(root: Path, relative: str) -> Path:
    """Resolve a relative asset path, refusing the root and paths outside it."""
    relative_path = Path(relative)
    if (not relative or relative_path.is_absolute() or PureWindowsPath(relative).is_absolute()
            or PureWindowsPath(relative).drive):
        raise ValueError("asset path must be relative")
    if any(part.rstrip(" .").casefold() == _STAGING_DIR for part in PureWindowsPath(relative).parts):
        raise ValueError("asset staging namespace is reserved")
    resolved_root = root.resolve()
    target = (resolved_root / relative_path).resolve()
    if target == resolved_root or not target.is_relative_to(resolved_root):
        raise ValueError("asset path outside storage root")
    if target.is_relative_to(resolved_root / _STAGING_DIR):
        raise ValueError("asset staging namespace is reserved")
    return target


def stage_asset(
    root: Path,
    relative: str,
    source: BinaryIO,
    *,
    validate: Callable[[Path], None] | None = None,
) -> Path:
    """Validate a temporary file and atomically link it as a new version.

    The destination must not already exist. Filesystems without hard-link
    support fail closed; the implementation never overwrites an old version.
    """
    storage_root = root.resolve(strict=True)
    target = resolve_asset_path(storage_root, relative)
    staging_dir = _staging_directory(storage_root, create=True)
    if staging_dir is None:
        raise OSError("staging directory unavailable")
    fd, name = tempfile.mkstemp(prefix=_STAGING_PREFIX, dir=staging_dir)
    staged = Path(name)
    committed = False
    try:
        with os.fdopen(fd, "wb") as output:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        if validate is not None:
            validate(staged)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = resolve_asset_path(storage_root, relative)
        os.link(staged, target)
        committed = True
        return target
    finally:
        try:
            staged.unlink(missing_ok=True)
        except OSError as exc:
            if committed:
                raise StageCommittedCleanupError(target) from exc
            raise
