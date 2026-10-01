"""Extract source text without discarding its physical location or whitespace."""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.file_types import CODE_EXTS, TEXT_EXTS
from app.services.parser import parse_file


@dataclass(frozen=True)
class LocatedText:
    logical_path: str
    text: str
    locator: dict[str, object]


def _located(logical_path: str, text: str, **position: object) -> LocatedText:
    return LocatedText(logical_path, text, {
        **position, "char_start": 0, "char_end": len(text),
        "line_start": 1, "line_end": text.count("\n") + 1,
    })


async def extract_documents(path: Path) -> list[LocatedText]:
    """Return pages, paragraphs, or raw text; positions are one-based, offsets zero-based."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            return [_located(f"page/{number}", page.extract_text() or "",
                             type="pdf_page", page=number)
                    for number, page in enumerate(pdf.pages, 1)]
    if suffix == ".docx":
        from docx import Document

        document: Any = Document(str(path))
        return [_located(f"paragraph/{number}", paragraph.text,
                         type="docx_paragraph", paragraph=number)
                for number, paragraph in enumerate(document.paragraphs, 1)]
    if suffix == ".doc":
        if shutil.which("libreoffice") is None:
            raise RuntimeError("LibreOffice 未安装，无法处理 .doc 文件")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / path.name
            shutil.copy2(path, source)
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "docx",
                 "--outdir", directory, str(source)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"文档转换失败: {result.stderr}")
            converted = source.with_suffix(".docx")
            if not converted.exists():
                raise RuntimeError("转换后的 .docx 文件未生成")
            return await extract_documents(converted)
    if suffix in CODE_EXTS | TEXT_EXTS:
        with path.open(encoding="utf-8", newline="") as source_file:
            text = source_file.read()
        return [_located("text", text, type="text")]
    # OCR has a document location but cannot claim original page or pixel positions.
    text = await parse_file(str(path))
    return [_located("text", text, type="ocr_text")]
