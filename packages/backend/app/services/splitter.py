"""文本切分引擎 ── 根据文档类型选择最优切分策略"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)


@dataclass
class Chunk:
    """切分后的文本片段"""
    content: str
    title: str = ""
    index: int = 0


# ── Markdown 按标题层级语义切分 ──

HEADERS_TO_SPLIT_ON: list[tuple[str, str]] = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
TOKENS_PER_CHUNK = 500


async def split_markdown(text: str) -> list[Chunk]:
    """Markdown：按 H1/H2/H3 语义切分，保持代码块完整"""
    splitter: Any = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    docs: Any = splitter.split_text(text)
    chunks: list[Chunk] = []
    for i, doc in enumerate(docs):
        # 如果单个 chunk 过长，二次按长度切分
        content: str = str(doc.page_content)
        if len(content) > CHUNK_SIZE * 2:
            sub_chunks = await _split_by_length(content)
            for sub in sub_chunks:
                sub.title = str(doc.metadata.get("h1", ""))
                chunks.append(sub)
        else:
            title_parts: list[str] = []
            if doc.metadata.get("h1"):
                title_parts.append(str(doc.metadata["h1"]))
            if doc.metadata.get("h2"):
                title_parts.append(str(doc.metadata["h2"]))
            chunks.append(
                Chunk(content=content, title=" > ".join(title_parts), index=i)
            )
    return chunks


async def split_pdf_or_docx(text: str) -> list[Chunk]:
    """PDF/Word：先按段落，再按长度 Token 分片"""
    # 按双换行切段落
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    current: list[str] = []
    current_len: int = 0

    for para in paragraphs:
        if current_len + len(para) > CHUNK_SIZE and current:
            chunks.append(Chunk(
                content="\n\n".join(current),
                title="",
                index=len(chunks),
            ))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append(Chunk(content="\n\n".join(current), title="", index=len(chunks)))

    # 再对过长 chunk 做 Token 切分
    final_chunks: list[Chunk] = []
    for ch in chunks:
        if len(ch.content) > CHUNK_SIZE * 2:
            sub = await _split_by_tokens(ch.content)
            final_chunks.extend(sub)
        else:
            final_chunks.append(ch)

    # 重新编号
    for i, ch in enumerate(final_chunks):
        ch.index = i
    return final_chunks


async def split_txt(text: str) -> list[Chunk]:
    """纯文本：递归字符切分 + 重叠窗口"""
    return await _split_by_length(text)


# ── 分发 ──


async def split_text(text: str, file_path: str = "") -> list[Chunk]:
    """根据文件类型自动选择切分策略"""
    suffix = Path(file_path).suffix.lower() if file_path else ""
    if suffix in (".md", ".markdown"):
        return await split_markdown(text)
    elif suffix in (".pdf", ".docx", ".doc"):
        return await split_pdf_or_docx(text)
    else:
        return await split_txt(text)


# ── 内部工具 ──


async def _split_by_length(text: str) -> list[Chunk]:
    """递归字符切分（通用回退策略）"""
    splitter: Any = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", ".", " ", ""],
    )
    docs: Any = splitter.create_documents([text])
    return [
        Chunk(content=str(d.page_content), index=i)
        for i, d in enumerate(docs)
    ]


async def _split_by_tokens(text: str) -> list[Chunk]:
    """Token 级别切分（用于二次细化过长的段落）"""
    splitter: Any = TokenTextSplitter(
        chunk_size=TOKENS_PER_CHUNK,
        chunk_overlap=50,
    )
    docs: Any = splitter.create_documents([text])
    return [
        Chunk(content=str(d.page_content), index=i)
        for i, d in enumerate(docs)
    ]
