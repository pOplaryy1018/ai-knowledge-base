"""Remove only tracked uploaded files after their database deletion commits."""

import logging
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"
# Earlier uploads used the package parent (or /uploads in a container).
LEGACY_UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "uploads"


def remove_uploads(paths: Iterable[str]) -> None:
    roots = (UPLOAD_ROOT.resolve(), LEGACY_UPLOAD_ROOT.resolve())
    for path in paths:
        target = Path(path).resolve()
        if not any(target.is_relative_to(root) for root in roots):
            logger.warning("Refused cleanup outside upload directory")
            continue
        try:
            target.unlink(missing_ok=True)
        except OSError:
            logger.exception("Upload cleanup failed for %s", target.name)
