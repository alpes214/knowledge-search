"""Markdown → list of `ChunkData`. Header-aware splitting plus recursive
character split for oversized sections. Stamps `page` and `heading_path`
on each chunk via the offset map."""
from __future__ import annotations

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from backend.app.config import settings
from backend.app.docs.loader import PageRange
from backend.app.repos.docs import ChunkData

# Tokens are roughly 4 chars on English text; pymupdf4llm's output is closer
# to 3.5–4. The langchain splitter is char-based, so we multiply by 4.
_CHARS_PER_TOKEN = 4

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def _heading_path(metadata: dict[str, str]) -> str | None:
    """Pick the deepest heading present, falling back upward."""
    for key in ("h3", "h2", "h1"):
        value = metadata.get(key)
        if value:
            return value
    return None


def split(markdown: str, page_ranges: list[PageRange]) -> list[ChunkData]:
    """Split a markdown document into chunks ready for embedding.

    Strategy: slice `markdown` per page first (using `page_ranges`), then run
    the header splitter on each page slice. This stamps `page` directly from
    the slice — no offset re-lookup, and no NULLs from splitter text mutation.
    `RecursiveCharacterTextSplitter` further splits any section that exceeds
    `docs_chunk_size` tokens. A heading from a previous page slice carries over
    until a new heading appears, so a section that spans pages keeps its
    heading on every chunk.

    Tradeoff: a heading section that spans pages becomes one chunk per page
    rather than one chunk total. Acceptable: each chunk still embeds with its
    surrounding heading context, and the page citation gets sharper.
    """
    if not markdown.strip():
        return []

    chunk_chars = settings.docs_chunk_size * _CHARS_PER_TOKEN
    overlap_chars = settings.docs_chunk_overlap * _CHARS_PER_TOKEN

    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS)
    recursive = RecursiveCharacterTextSplitter(
        chunk_size=chunk_chars,
        chunk_overlap=overlap_chars,
    )

    slices: list[tuple[str, int | None]]
    if page_ranges:
        slices = [
            (markdown[r.start_offset:r.end_offset], r.page_number)
            for r in page_ranges
        ]
    else:
        slices = [(markdown, None)]

    chunks: list[ChunkData] = []
    current_heading: str | None = None
    for page_text, page_number in slices:
        if not page_text.strip():
            continue
        for section in header_splitter.split_text(page_text):
            section_text = section.page_content.strip()
            if not section_text:
                continue
            section_heading = _heading_path(section.metadata)
            if section_heading is not None:
                current_heading = section_heading
            heading = current_heading

            sub_texts = (
                recursive.split_text(section_text)
                if len(section_text) > chunk_chars
                else [section_text]
            )
            for sub in sub_texts:
                sub = sub.strip()
                if not sub:
                    continue
                chunks.append(
                    ChunkData(
                        text=sub,
                        embedding=[],
                        page=page_number,
                        heading=heading,
                    )
                )
    return chunks
