from dataclasses import dataclass

from app.services.source_extraction import LocatedText


class ConnectorError(ValueError):
    pass


class SnapshotLimitError(ConnectorError):
    pass


@dataclass(frozen=True)
class SnapshotLimits:
    max_files: int = 5000
    max_file_bytes: int = 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024
    timeout_seconds: float = 180


@dataclass(frozen=True)
class Snapshot:
    commit: str
    documents: list[LocatedText]
    manifest: dict[str, object]
    dirty: bool
    config_fingerprint: str


DEFAULT_LIMITS = SnapshotLimits()
