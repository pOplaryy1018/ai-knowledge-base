"""Immutable image evidence connector."""

import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from app.services.source_extraction import LocatedText

from .types import ConnectorError, SnapshotLimitError

PIPELINE_VERSION = "image-raw-v1"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_TEXT_CHARS = 100_000
OCR_TIMEOUT_SECONDS = 30
OCRStatus = Literal["completed", "no_text", "unavailable"]
FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}


@dataclass(frozen=True)
class ValidatedImage:
    original_bytes: bytes
    image_hash: str
    format: str
    width: int
    height: int


@dataclass(frozen=True, init=False)
class ImageSnapshot:
    image_hash: str
    ocr_text: str
    ocr_status: OCRStatus
    manual_description: str
    ocr_correction: str
    raw_hash: str
    _documents: tuple[tuple[str, str, str], ...]
    _manifest: str

    def __init__(
        self, image_hash: str, ocr_text: str, ocr_status: OCRStatus,
        manual_description: str, ocr_correction: str, raw_hash: str,
        documents: list[LocatedText], manifest: dict[str, object],
    ) -> None:
        # Nested evidence is stored only as immutable tuples/JSON strings. Public
        # access reconstructs ordinary list/dict values for existing consumers.
        for name, value in (
            ("image_hash", image_hash), ("ocr_text", ocr_text),
            ("ocr_status", ocr_status), ("manual_description", manual_description),
            ("ocr_correction", ocr_correction), ("raw_hash", raw_hash),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(self, "_documents", tuple(
            (doc.logical_path, doc.text, json.dumps(doc.locator, ensure_ascii=False))
            for doc in documents
        ))
        object.__setattr__(self, "_manifest", json.dumps(manifest, ensure_ascii=False))

    @property
    def documents(self) -> list[LocatedText]:
        return [LocatedText(path, text, json.loads(locator))
                for path, text, locator in self._documents]

    @property
    def manifest(self) -> dict[str, object]:
        result: dict[str, object] = json.loads(self._manifest)
        return result


def validate_image(path: str | Path) -> ValidatedImage:
    """Decode bounded original bytes, matching the declared extension and format."""
    path = Path(path)
    expected = FORMATS.get(path.suffix.lower())
    if expected is None:
        raise ConnectorError("Unsupported image extension")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise SnapshotLimitError("Image byte limit exceeded")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != expected:
                raise ConnectorError("Image format does not match extension")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise SnapshotLimitError("Image pixel limit exceeded")
            if getattr(image, "n_frames", 1) != 1:
                raise ConnectorError("Animated images are unsupported")
            width, height = image.size
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        if isinstance(exc, ConnectorError):
            raise
        raise ConnectorError("Invalid image") from None
    return ValidatedImage(raw, hashlib.sha256(raw).hexdigest(), expected, width, height)


def _bounded_text(text: str) -> str:
    if len(text) > MAX_TEXT_CHARS:
        raise SnapshotLimitError("Image text limit exceeded")
    return text if text.strip() else ""


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def build_image_snapshot(
    image_hash: str,
    *,
    ocr_text: str,
    ocr_status: OCRStatus,
    manual_description: str = "",
    ocr_correction: str = "",
    image_metadata: dict[str, object] | None = None,
) -> ImageSnapshot:
    """Build a revision from retained machine OCR, without executing OCR again."""
    if len(image_hash) != 64 or any(c not in "0123456789abcdef" for c in image_hash):
        raise ConnectorError("Invalid image hash")
    ocr_text = _bounded_text(ocr_text)
    manual_description = _bounded_text(manual_description)
    ocr_correction = _bounded_text(ocr_correction)
    if ocr_status not in {"completed", "no_text", "unavailable"}:
        raise ConnectorError("Invalid OCR status")
    if bool(ocr_text) != (ocr_status == "completed"):
        raise ConnectorError("OCR status does not match text")
    channels = {
        "ocr_text": ocr_text,
        "ocr_correction": ocr_correction,
        "manual_description": manual_description,
    }
    documents = []
    retrieval = (
        [("ocr_correction", ocr_correction, "image_ocr_correction")]
        if ocr_correction
        else [("ocr_text", ocr_text, "image_ocr")]
    )
    retrieval.append(("manual_description", manual_description, "manual_description"))
    for logical_path, text, origin in retrieval:
        if text:
            documents.append(LocatedText(logical_path, text, {
                "type": "image", "origin": origin, "image_hash": image_hash,
                "char_start": 0, "char_end": len(text),
                "line_start": 1, "line_end": text.count("\n") + 1,
            }))
    fingerprints = {name: _fingerprint(text) for name, text in channels.items()}
    content = {
        "pipeline_version": PIPELINE_VERSION, "image_hash": image_hash,
        "ocr_status": ocr_status, **channels,
    }
    # Only known, bounded metadata is retained; no paths or raw exception details.
    metadata = {
        key: value for key, value in (image_metadata or {}).items()
        if (key == "format" and isinstance(value, str) and value in {"PNG", "JPEG", "WEBP"})
        or (key in {"width", "height", "bytes"} and type(value) is int
            and 0 <= value <= MAX_IMAGE_BYTES)
    }
    manifest: dict[str, object] = {
        **content, "channel_fingerprints": fingerprints, "image": metadata,
    }
    return ImageSnapshot(image_hash, ocr_text, ocr_status, manual_description,
                         ocr_correction, _fingerprint(content), documents, manifest)


def _default_ocr(image: Image.Image) -> str:
    import pytesseract

    return str(pytesseract.image_to_string(
        image, lang="chi_sim+eng", timeout=OCR_TIMEOUT_SECONDS,
    ))


def collect_image(
    path: str | Path,
    *,
    manual_description: str = "",
    ocr_correction: str = "",
    ocr_runner: Callable[[Image.Image], str] | None = None,
) -> ImageSnapshot:
    validated = validate_image(path)
    # Reject invalid user text before running an external OCR process.
    manual_description = _bounded_text(manual_description)
    ocr_correction = _bounded_text(ocr_correction)
    status: OCRStatus = "unavailable"
    text = ""
    try:
        with Image.open(io.BytesIO(validated.original_bytes)) as image:
            text = _bounded_text((ocr_runner or _default_ocr)(image))
        status = "completed" if text else "no_text"
    except Exception:
        # Valid originals remain evidence even when OCR installation/runtime fails.
        text = ""
    return build_image_snapshot(
        validated.image_hash, ocr_text=text, ocr_status=status,
        manual_description=manual_description, ocr_correction=ocr_correction,
        image_metadata={"format": validated.format, "width": validated.width,
                        "height": validated.height, "bytes": len(validated.original_bytes)},
    )
