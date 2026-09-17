"""Download utilities for auction result PDFs."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable, Tuple

import requests

from .config import download as dl_cfg, paths
from .discovery.pvrm_index import DiscoveredPDF


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def category_dir(category: str) -> str:
    if category.upper() == "PVRM":
        return paths.raw_pvrm
    return paths.raw_tvrm


def local_filename(pdf: DiscoveredPDF) -> str:
    base = os.path.basename(pdf.url.split("?", 1)[0]) or "auction.pdf"
    return os.path.join(category_dir(pdf.category), base)


def download_pdf(pdf: DiscoveredPDF) -> Tuple[str, str]:
    """Download a single PDF if needed.

    Returns (local_path, sha256_hash).
    """

    out_dir = category_dir(pdf.category)
    _ensure_dir(out_dir)
    local_path = local_filename(pdf)

    if os.path.exists(local_path):
        # Compute hash of existing file
        return local_path, _sha256_of_file(local_path)

    for attempt in range(1, dl_cfg.max_retries + 1):
        try:
            resp = requests.get(pdf.url, timeout=dl_cfg.timeout_seconds)
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(resp.content)
            file_hash = _sha256_of_file(local_path)
            return local_path, file_hash
        except requests.RequestException:
            if attempt == dl_cfg.max_retries:
                raise


def _sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


