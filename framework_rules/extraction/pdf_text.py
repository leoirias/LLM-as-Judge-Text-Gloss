"""Extração de texto por faixa de páginas do PDF do livro."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def extract_pages(pdf_path: Path, start_page: int, end_page: int) -> str:
    """Texto das páginas [start_page, end_page], inclusive, 0-indexadas (índice
    do pypdf / destinos do outline do PDF — NÃO o número impresso na página, que
    tem offset por causa das páginas iniciais). Cada página é prefixada por um
    marcador [p.N] com esse mesmo índice, para que a `fonte_pagina` citada por
    uma regra fique consistente com a faixa usada para selecionar o capítulo."""
    reader = PdfReader(str(pdf_path))
    chunks = []
    for i in range(start_page, end_page + 1):
        text = reader.pages[i].extract_text() or ""
        chunks.append(f"[p.{i}]\n{text}")
    return "\n\n".join(chunks)
