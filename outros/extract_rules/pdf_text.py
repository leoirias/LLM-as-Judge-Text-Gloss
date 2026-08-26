"""Page-range text extraction from the ASL grammar book."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def extract_pages(pdf_path: Path, start_page: int, end_page: int) -> str:
    """Extract text for pages [start_page, end_page], inclusive, 0-indexed
    (matching pypdf's page indices / the PDF outline's destination numbers —
    NOT the book's printed page numbers, which are offset by front matter).
    Each page is prefixed with a [p.N] marker using that same 0-indexed
    number, so a rule's cited source_page stays consistent with the
    start_page/end_page used to select the chapter."""
    reader = PdfReader(str(pdf_path))
    chunks = []
    for i in range(start_page, end_page + 1):
        text = reader.pages[i].extract_text() or ""
        chunks.append(f"[p.{i}]\n{text}")
    return "\n\n".join(chunks)
