"""Discover Traditional VRM (TVRM) auction PDFs via index pages."""

from __future__ import annotations

from typing import Iterable

from .pvrm_index import DiscoveredPDF, _extract_pdfs_from_page, _full_url
from ..config import discovery


def discover_tvrm_pdfs() -> Iterable[DiscoveredPDF]:
    """Yield TVRM auction result PDFs from the TD TVRM index page."""

    index_url = _full_url(discovery.tvrm_index_path)
    for pdf in _extract_pdfs_from_page(index_url):
        pdf.category = "TVRM"
        yield pdf


