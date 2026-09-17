"""Discover Personalized VRM (PVRM) auction result PDFs from TD index pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import requests
from bs4 import BeautifulSoup

from ..config import discovery


@dataclass
class DiscoveredPDF:
    category: str  # "PVRM" or "TVRM"
    url: str
    label: str
    source_page: str


def _full_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return discovery.base_url.rstrip("/") + path


def _extract_pdfs_from_page(url: str) -> List[DiscoveredPDF]:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    # TD pages are UTF-8; requests may guess ISO-8859-1 from missing/wrong headers.
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.content, "html.parser", from_encoding="utf-8")

    found: List[DiscoveredPDF] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue

        label = (a.get_text(strip=True) or href).lower()

        # Keep auction-result PDFs; drop venue maps / guidance notes.
        exclude = ["access map", "guidance notes", "road%20map", "roadmap", "road map"]
        if any(x in href.lower() or x in label for x in exclude):
            continue
        keep_keywords = ["auction", "結果", "成績", "result", "handout", "pvrm"]
        if not any(keyword in label or keyword in href.lower() for keyword in keep_keywords):
            continue

        found.append(
            DiscoveredPDF(
                category="PVRM",
                url=_full_url(href),
                label=a.get_text(strip=True) or href,
                source_page=url,
            )
        )
    return found


def discover_pvrm_pdfs() -> Iterable[DiscoveredPDF]:
    """Yield PVRM auction result PDFs found on the TD index page.

    This function only follows the main index page. If the TD site provides
    additional archive pages linked from there, they can be discovered by
    extending this function in the future.
    """

    index_url = _full_url(discovery.pvrm_index_path)
    yield from _extract_pdfs_from_page(index_url)


