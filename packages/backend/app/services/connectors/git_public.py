"""Fetch only canonical public GitHub HTTPS URLs into a disposable bare cache."""

import re
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from .git_local import _check_chain
from .git_snapshot import extract_snapshot, run_git
from .types import DEFAULT_LIMITS, ConnectorError, Snapshot, SnapshotLimits


def canonical_public_url(url: str) -> str:
    url = url.rstrip("/")
    match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9_.-]+?)(?:\.git)?", url
    )
    if not match or match.group(2) in {".", ".."} or match.group(2).startswith("-"):
        raise ConnectorError("Only canonical HTTPS GitHub owner/repo URLs are accepted")
    return f"https://github.com/{match.group(1)}/{match.group(2)}.git"


def collect_public(
    url: str,
    *,
    cache_root: str | Path,
    git_executable: str = "git",
    limits: SnapshotLimits = DEFAULT_LIMITS,
    include_paths: Sequence[str] = (),
) -> Snapshot:
    remote = canonical_public_url(url)
    root = Path(cache_root).absolute()
    _check_chain(root)
    root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + limits.timeout_seconds
    with tempfile.TemporaryDirectory(prefix="public-git-", dir=root) as directory:
        repo = Path(directory)
        run_git(repo, ["init", "--bare", "."], git_executable=git_executable, deadline=deadline)
        run_git(
            repo,
            [
                "-c",
                "protocol.allow=never",
                "-c",
                "protocol.https.allow=always",
                "-c",
                "http.extraHeader=",
                "-c",
                "http.proxy=",
                "fetch",
                "--depth=1",
                "--no-tags",
                "--no-recurse-submodules",
                remote,
                "HEAD",
            ],
            git_executable=git_executable,
            deadline=deadline,
            storage_budget=limits.max_total_bytes * 2,
        )
        run_git(
            repo,
            ["update-ref", "HEAD", "FETCH_HEAD"],
            git_executable=git_executable,
            deadline=deadline,
        )
        return extract_snapshot(
            repo,
            git_executable=git_executable,
            limits=limits,
            include_paths=include_paths,
            deadline=deadline,
        )
