"""High-level orchestration: discover → download → parse → store."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Iterable, List, Optional

import fitz

from . import db
from .dates import extract_date_from_candidates
from .discovery import (
    discover_pvrm_pdfs,
    discover_tvrm_pdfs,
    discover_tvrm_pdfs_from_templates,
)
from .discovery.pvrm_index import DiscoveredPDF
from .download import download_pdf
from .models import AuctionEvent
from .parsing import parse_pvrm_pdf, parse_tvrm_pdf

logger = logging.getLogger(__name__)


def run_discovery(include_templates: bool = False) -> List[DiscoveredPDF]:
    """Run discovery strategies and return de-duplicated PDFs.

    Template probing is opt-in because it can issue thousands of HEAD requests.
    """

    discovered: List[DiscoveredPDF] = []
    discovered.extend(list(discover_pvrm_pdfs()))
    discovered.extend(list(discover_tvrm_pdfs()))
    if include_templates:
        discovered.extend(list(discover_tvrm_pdfs_from_templates()))
    unique = {d.url: d for d in discovered}
    return list(unique.values())


def _infer_auction_date(pdf: DiscoveredPDF, local_path: str) -> Optional[date]:
    candidates = [pdf.label, pdf.url, local_path]
    try:
        doc = fitz.open(local_path)
        header = "\n".join(doc[0].get_text().splitlines()[:8])
        candidates.insert(0, header)
    except Exception:
        pass
    return extract_date_from_candidates(candidates)


def run_download_and_parse(pdfs: Iterable[DiscoveredPDF]) -> None:
    """Download each discovered PDF, parse it, and persist to the DB."""

    db.init_db()

    for pdf in pdfs:
        local_path, file_hash = download_pdf(pdf)

        if pdf.category.upper() == "PVRM":
            lots = parse_pvrm_pdf(local_path)
        else:
            lots = parse_tvrm_pdf(local_path)

        if not lots:
            logger.warning("No lots parsed from %s (%s)", local_path, pdf.url)
            continue

        event = AuctionEvent(
            id=None,
            category=pdf.category.upper(),
            auction_date=_infer_auction_date(pdf, local_path),
            source_pdf_url=pdf.url,
            source_pdf_filename=local_path,
            source_pdf_hash=file_hash,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        event_id = db.upsert_auction_event(event)

        for lot in lots:
            lot.auction_event_id = event_id

        db.insert_auction_lots(event_id, lots)
        logger.info(
            "Stored %s lots for %s on %s",
            len(lots),
            event.category,
            event.auction_date,
        )
