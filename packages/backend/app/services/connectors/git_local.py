"""Authorized local repositories; never follow repository indirection."""

import os
import re
import time
from collections.abc import Sequence
from pathlib import Path

from .git_snapshot import extract_snapshot, run_git
from .types import DEFAULT_LIMITS, ConnectorError, Snapshot, SnapshotLimits


def _check_chain(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ConnectorError("Symbolic repository paths are forbidden")


def collect_local(
    repo_path: str | Path,
    *,
    allowed_roots: Sequence[str | Path],
    authorized: bool,
    git_executable: str = "git",
    limits: SnapshotLimits = DEFAULT_LIMITS,
    include_paths: Sequence[str] = (),
) -> Snapshot:
    if not authorized:
        raise ConnectorError("Repository access denied")
    deadline = time.monotonic() + limits.timeout_seconds
    original = Path(repo_path).absolute()
    _check_chain(original)
    repo = original.resolve(strict=True)
    if not any(repo.is_relative_to(Path(root).resolve()) for root in allowed_roots):
        raise ConnectorError("Repository outside authorized roots")
    gitdir = repo / ".git"
    _check_chain(gitdir)
    if not gitdir.is_dir():
        raise ConnectorError("Linked worktrees and indirect Git directories are forbidden")
    # Git can follow object alternates and repository configuration includes.
    pending = [gitdir]
    inspected = 0
    while pending:
        if time.monotonic() >= deadline:
            raise ConnectorError("Repository inspection timed out")
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                inspected += 1
                if inspected > 100000:
                    raise ConnectorError("Repository metadata inspection limit exceeded")
                target = Path(entry.path)
                _check_chain(target)
                if entry.is_dir(follow_symlinks=False):
                    pending.append(target)
    if (gitdir / "objects/info/alternates").exists() or (
        gitdir / "objects/info/http-alternates"
    ).exists():
        raise ConnectorError("Object alternates forbidden")
    config = (gitdir / "config").read_text(encoding="utf-8")
    if re.search(r"\[\s*(include|filter)", config, re.IGNORECASE) or any(
        token in config.lower()
        for token in (
            "[include",
            "[filter",
            "worktreeconfig",
            "commondir",
            "extensions.partialclone",
            "promisor",
            "gitdir",
            "worktree =",
            "worktree=",
        )
    ):
        raise ConnectorError("Repository configuration indirection forbidden")
    if (gitdir / "commondir").exists() or (gitdir / "config.worktree").exists():
        raise ConnectorError("Worktree indirection forbidden")
    dirty = bool(
        run_git(
            repo,
            ["status", "--porcelain", "--untracked-files=normal"],
            git_executable=git_executable,
            deadline=deadline,
        )
    )
    return extract_snapshot(
        repo,
        git_executable=git_executable,
        limits=limits,
        include_paths=include_paths,
        dirty=dirty,
        deadline=deadline,
    )
