"""Central configuration for the car_auction project.

All paths are expressed relative to the project root by default so that
no user-specific absolute paths need to be hard-coded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _default(path: str) -> str:
    return os.path.join(PROJECT_ROOT, path)


@dataclass(frozen=True)
class Paths:
    """Filesystem layout used by the pipeline."""

    data_root: str = _default("data")
    raw_pvrm: str = _default("data/raw/pvrm")
    raw_tvrm: str = _default("data/raw/tvrm")
    processed: str = _default("data/processed")
    db_path: str = _default("data/db/auction.db")


@dataclass(frozen=True)
class DiscoverySettings:
    """Settings related to PDF discovery on the TD website."""

    base_url: str = "https://www.td.gov.hk"
    pvrm_index_path: str = "/tc/public_services/vehicle_registration_mark/pvrm_auction/index.html"
    tvrm_index_path: str = "/tc/public_services/vehicle_registration_mark/tvrm_auction/index.html"

    # Historical search start dates (conservative; can be adjusted by user)
    pvrm_start_date: date = date(1990, 1, 1)
    tvrm_start_date: date = date(1973, 1, 1)


@dataclass(frozen=True)
class DownloadSettings:
    timeout_seconds: int = 20
    max_retries: int = 3


@dataclass(frozen=True)
class ParsingSettings:
    """Parameters controlling PDF parsing heuristics."""

    max_pages: int | None = None  # allow limiting pages per PDF if needed
    # Whether to enable an OCR-based fallback when text extraction from
    # a PDF page yields too little content to be useful. This is primarily
    # intended for older scanned documents.
    use_ocr_fallback: bool = True
    # OCR engine identifier – currently only "paddle" is supported but this
    # leaves room for future alternatives.
    # "auto" prefers RapidOCR, then PaddleOCR if installed.
    ocr_engine: str = "auto"


paths = Paths()
discovery = DiscoverySettings()
download = DownloadSettings()
parsing = ParsingSettings()
