"""文档解析引擎 ── 将 PDF/Word/Markdown/TXT/图片 提取为纯文本"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def parse_pdf(file_path: str) -> str:
    """PDF 解析：逐页提取文本"""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


async def parse_docx(file_path: str) -> str:
    """Word .docx 解析：提取段落文本"""
    from docx import Document

    doc: Any = Document(file_path)
    paragraphs: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text.strip())
    return "\n\n".join(paragraphs)


async def parse_doc(file_path: str) -> str:
    """.doc (Word 97-2003 OLE2 格式) 解析：LibreOffice headless 转 .docx → python-docx 提取"""
    if shutil.which("libreoffice") is None:
        raise RuntimeError("LibreOffice 未安装，无法处理 .doc 文件")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        src = tmp_path / Path(file_path).name
        shutil.copy2(file_path, src)

        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to", "docx",
                "--outdir", str(tmpdir),
                str(src),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.error("LibreOffice 转换失败: %s", result.stderr)
            raise RuntimeError(f"文档转换失败: {result.stderr}")

        docx_file = tmp_path / f"{Path(file_path).stem}.docx"
        if not docx_file.exists():
            raise RuntimeError("转换后的 .docx 文件未生成")

        return await parse_docx(str(docx_file))


async def parse_image(file_path: str) -> str:
    """图片 OCR 解析：pytesseract + Pillow，支持中英文混合识别"""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise ImportError("OCR 服务未安装（缺少 pytesseract 或 Pillow），无法处理图片文件")

    img = Image.open(file_path)
    text = pytesseract.image_to_string(img, lang="chi_sim+eng")
    if not text.strip():
        raise ValueError("图片中未检测到可识别文字")
    return text.strip()


async def parse_markdown(file_path: str) -> str:
    """Markdown 解析：直接读取原文本（保留格式用于后续结构化切分）"""
    return Path(file_path).read_text(encoding="utf-8")


async def parse_txt(file_path: str) -> str:
    """纯文本解析"""
    return Path(file_path).read_text(encoding="utf-8")


# ── 格式分发映射 ──
PARSER_MAP: dict[str, Any] = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".doc": parse_doc,
    ".md": parse_markdown,
    ".markdown": parse_markdown,
    ".txt": parse_txt,
    ".text": parse_txt,
    ".png": parse_image,
    ".jpg": parse_image,
    ".jpeg": parse_image,
    ".gif": parse_image,
    ".bmp": parse_image,
    ".webp": parse_image,
}


async def parse_file(file_path: str) -> str:
    """根据文件扩展名自动选择解析器"""
    suffix = Path(file_path).suffix.lower()
    parser = PARSER_MAP.get(suffix)
    if parser is None:
        raise ValueError(f"不支持的文件格式: {suffix}，支持的格式: {list(PARSER_MAP.keys())}")
    text: str = await parser(file_path)
    if not text.strip():
        raise ValueError("文档解析结果为空，请检查文件内容")
    return text
