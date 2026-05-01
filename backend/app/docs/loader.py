"""PDF → Markdown via pymupdf4llm. Emits per-page offset map."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pymupdf
import pymupdf4llm


@dataclass(frozen=True)
class PageRange:
    """Maps a half-open `[start_offset, end_offset)` slice of the concatenated
    markdown back to a 1-based source page number."""

    start_offset: int
    end_offset: int
    page_number: int


def pdf_to_markdown(file_bytes: bytes) -> tuple[str, list[PageRange]]:
    """Convert PDF bytes to a single concatenated markdown string plus a list
    of `PageRange` records describing which characters came from which page.

    Pages are joined with `\\n\\n`. Page numbers are 1-based.
    """
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    try:
        pages: list[dict[str, Any]] = pymupdf4llm.to_markdown(doc, page_chunks=True)
    finally:
        doc.close()  # type: ignore[no-untyped-call]

    parts: list[str] = []
    ranges: list[PageRange] = []
    cursor = 0
    separator = "\n\n"
    for index, page in enumerate(pages, start=1):
        text = page.get("text", "")
        meta = page.get("metadata") or {}
        # pymupdf4llm uses `metadata.page_number` (1-based) in current versions;
        # older versions used `metadata.page` (0-based). Fall back to the loop
        # index to stay robust across versions.
        page_no_raw = meta.get("page_number")
        if isinstance(page_no_raw, int):
            page_no = page_no_raw
        elif isinstance(meta.get("page"), int):
            page_no = meta["page"] + 1
        else:
            page_no = index
        start = cursor
        parts.append(text)
        cursor += len(text)
        end = cursor
        ranges.append(PageRange(start_offset=start, end_offset=end, page_number=page_no))
        parts.append(separator)
        cursor += len(separator)
    # Drop the trailing separator from the last page.
    if parts and parts[-1] == separator:
        parts.pop()
        cursor -= len(separator)
    markdown = "".join(parts)
    return markdown, ranges


def page_for_offset(ranges: list[PageRange], offset: int) -> int | None:
    """Return the page number whose `[start_offset, end_offset)` contains
    `offset`, or `None` if the offset falls outside any range."""
    for r in ranges:
        if r.start_offset <= offset < r.end_offset:
            return r.page_number
    return None
