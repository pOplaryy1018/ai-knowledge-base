"""Read immutable Git blobs, preserving their original UTF-8 text."""

import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path, PurePosixPath

from app.services.source_extraction import LocatedText

from .types import DEFAULT_LIMITS, ConnectorError, Snapshot, SnapshotLimitError, SnapshotLimits

PIPELINE_VERSION = "git-raw-v1"


def safe_env(isolated_home: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    env.update(
        HOME=isolated_home,
        USERPROFILE=isolated_home,
        XDG_CONFIG_HOME=isolated_home,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_ASKPASS="",
        SSH_ASKPASS="",
        GIT_LFS_SKIP_SMUDGE="1",
    )
    return env


def run_git(
    repo: str | Path,
    args: Sequence[str],
    *,
    git_executable: str = "git",
    deadline: float | None = None,
    storage_budget: int | None = None,
) -> bytes:
    remaining = 180 if deadline is None else deadline - time.monotonic()
    if remaining <= 0:
        raise SnapshotLimitError("Git collection timed out")
    argv = [
        git_executable,
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "credential.helper=",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.attributesFile=" + os.devnull,
        "-c",
        "protocol.file.allow=never",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "http.followRedirects=false",
        "-C",
        str(repo),
        *args,
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="git-empty-home-") as isolated_home:
            if storage_budget is None:
                result = subprocess.run(
                    argv,
                    env=safe_env(isolated_home),
                    capture_output=True,
                    timeout=remaining,
                    shell=False,
                )
            else:
                # Disk-backed output prevents a verbose fetch from filling pipes or RAM.
                with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
                    process = subprocess.Popen(
                        argv, env=safe_env(isolated_home), stdout=output, stderr=errors, shell=False
                    )
                    try:
                        while process.poll() is None:
                            size = output.tell() + errors.tell()
                            for directory, _, filenames in os.walk(repo):
                                for filename in filenames:
                                    with suppress(FileNotFoundError):
                                        size += os.stat(os.path.join(directory, filename)).st_size
                                    if size > storage_budget:
                                        raise SnapshotLimitError("Fetch storage limit exceeded")
                            if size > storage_budget:
                                raise SnapshotLimitError("Fetch storage limit exceeded")
                            if deadline is not None and time.monotonic() >= deadline:
                                raise SnapshotLimitError("Git collection timed out")
                            time.sleep(0.05)
                        # Check final size as well, including fetches shorter than the polling interval.
                        size = output.tell() + errors.tell()
                        for directory, _, filenames in os.walk(repo):
                            for filename in filenames:
                                size += os.stat(os.path.join(directory, filename)).st_size
                        if size > storage_budget:
                            raise SnapshotLimitError("Fetch storage limit exceeded")
                        output.seek(0)
                        result = subprocess.CompletedProcess(
                            argv, process.returncode, output.read(), b""
                        )
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait()

    except subprocess.TimeoutExpired as exc:
        raise SnapshotLimitError("Git collection timed out") from exc
    except OSError as exc:
        raise ConnectorError("Git executable unavailable") from exc
    if result.returncode:
        raise ConnectorError("Git command failed")
    return result.stdout


def skip_reason(path: str, mode: str) -> str | None:
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    if mode != "100644" and mode != "100755":
        return "non_regular"
    if (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
        or name in {"id_rsa", "id_ed25519", "credentials"}
    ):
        return "sensitive"
    if any(
        p.lower() in {"node_modules", "dist", "vendor", "build", ".next", "__pycache__"}
        for p in parts
    ):
        return "excluded_directory"
    return None


def extract_snapshot(
    repo: str | Path,
    *,
    git_executable: str = "git",
    limits: SnapshotLimits = DEFAULT_LIMITS,
    include_paths: Sequence[str] = (),
    dirty: bool = False,
    deadline: float | None = None,
) -> Snapshot:
    deadline = deadline or time.monotonic() + limits.timeout_seconds
    commit = (
        run_git(
            repo,
            ["rev-parse", "--verify", "HEAD^{commit}"],
            git_executable=git_executable,
            deadline=deadline,
        )
        .decode()
        .strip()
    )
    tree = run_git(
        repo,
        ["ls-tree", "-r", "-z", "--long", commit],
        git_executable=git_executable,
        deadline=deadline,
    )
    entries = [entry for entry in tree.split(b"\0") if entry]
    documents = []
    skipped = []
    files = []
    total = 0
    candidates = 0
    for entry in entries:
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid, size = metadata.decode().split()
        path = raw_path.decode("utf-8", errors="strict")
        reason = skip_reason(path, mode)
        if include_paths and not any(
            path == p or path.startswith(p.rstrip("/") + "/") for p in include_paths
        ):
            reason = "outside_scope"
        if reason:
            skipped.append({"path": path, "reason": reason})
            continue
        candidates += 1
        if candidates > limits.max_files:
            raise SnapshotLimitError("Candidate file limit exceeded")
        length = int(size)
        if length > limits.max_file_bytes:
            raise SnapshotLimitError("Single file byte limit exceeded")
        if total + length > limits.max_total_bytes:
            raise SnapshotLimitError("Total byte limit exceeded")
        raw = run_git(
            repo, ["cat-file", "blob", oid], git_executable=git_executable, deadline=deadline
        )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": path, "reason": "binary"})
            continue
        if "\x00" in text:
            skipped.append({"path": path, "reason": "binary"})
            continue
        if "-----BEGIN " in text and "PRIVATE KEY-----" in text:
            skipped.append({"path": path, "reason": "sensitive"})
            continue
        total += length
        documents.append(
            LocatedText(
                path,
                text,
                {
                    "type": "git",
                    "path": path,
                    "commit": commit,
                    "line_start": 1,
                    "line_end": text.count("\n") + 1,
                    "char_start": 0,
                    "char_end": len(text),
                },
            )
        )
        files.append({"path": path, "oid": oid, "bytes": length})
    config = {
        "pipeline_version": PIPELINE_VERSION,
        "include_paths": sorted(include_paths),
        "limits": limits.__dict__,
    }
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return Snapshot(
        commit,
        documents,
        {
            "complete": True,
            "files": files,
            "skipped": skipped,
            "stats": {
                "candidates": len(entries),
                "included": len(files),
                "skipped": len(skipped),
                "text_bytes": total,
            },
            **config,
        },
        dirty,
        fingerprint,
    )
