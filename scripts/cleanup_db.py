"""Backfill dates, remove local:// duplicates, and fix misclassified parses."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from car_auction import db
from car_auction.dates import extract_date_from_candidates, extract_date_from_text
from car_auction.discovery.pvrm_index import discover_pvrm_pdfs
from car_auction.models import AuctionEvent
from car_auction.parsing.pvrm import parse_pvrm_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cleanup")


def _filename(url_or_path: str) -> str:
    return unquote(url_or_path.rstrip("/").rsplit("/", 1)[-1]).lower()


def backfill_dates() -> int:
    url_labels: dict[str, str] = {}
    for pdf in discover_pvrm_pdfs():
        url_labels[pdf.url] = pdf.label or ""
        url_labels[_filename(pdf.url)] = pdf.label or ""

    updated = 0
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, category, source_pdf_url, source_pdf_filename, auction_date
            FROM auction_events
            WHERE auction_date IS NULL OR auction_date = ''
            """
        ).fetchall()

        for eid, category, url, path, _ in rows:
            label = url_labels.get(url) or url_labels.get(_filename(url), "")
            candidates = [label, unquote(url), unquote(path), Path(unquote(path)).name]
            try:
                import fitz

                doc = fitz.open(path)
                header = "\n".join(doc[0].get_text().splitlines()[:12])
                candidates.insert(0, header)
            except Exception:
                pass
            inferred = extract_date_from_candidates(candidates)
            if not inferred:
                continue
            conn.execute(
                "UPDATE auction_events SET auction_date = ?, updated_at = ? WHERE id = ?",
                (inferred.isoformat(), datetime.now(timezone.utc).isoformat(), eid),
            )
            updated += 1
            logger.info("Backfilled event %s -> %s (%s)", eid, inferred, _filename(url))
    return updated


def remove_local_duplicates() -> int:
    removed = 0
    with db.get_connection() as conn:
        locals_ = conn.execute(
            "SELECT id, source_pdf_url FROM auction_events WHERE source_pdf_url LIKE 'local://%'"
        ).fetchall()
        https_names = {
            _filename(r[0])
            for r in conn.execute(
                "SELECT source_pdf_url FROM auction_events WHERE source_pdf_url LIKE 'http%'"
            ).fetchall()
        }
        for eid, url in locals_:
            name = _filename(url)
            if name in https_names:
                conn.execute("DELETE FROM auction_lots WHERE auction_event_id = ?", (eid,))
                conn.execute("DELETE FROM auction_events WHERE id = ?", (eid,))
                removed += 1
                logger.info("Removed local duplicate event %s (%s)", eid, name)
    return removed


def fix_misclassified_pvrm() -> None:
    """auction results handout_20110108.pdf is a PVRM handout, not TVRM."""

    target_names = {"auction results handout_20110108.pdf", "auction%20results%20handout_20110108.pdf"}
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT id, source_pdf_url, source_pdf_filename, source_pdf_hash FROM auction_events"
        ).fetchall()
        for eid, url, path, file_hash in rows:
            if _filename(url) not in {n.lower() for n in target_names} and _filename(path) not in {
                n.lower() for n in target_names
            }:
                continue
            lots = parse_pvrm_pdf(path)
            if len(lots) < 20:
                logger.warning("Skip reparse %s; only %s lots", url, len(lots))
                continue
            auction_date = extract_date_from_text(unquote(url)) or extract_date_from_text(path)
            event = AuctionEvent(
                id=None,
                category="PVRM",
                auction_date=auction_date,
                source_pdf_url=url if url.startswith("http") else (
                    "https://www.td.gov.hk/filemanager/common/auction%20results%20handout_20110108.pdf"
                ),
                source_pdf_filename=path,
                source_pdf_hash=file_hash,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            # If replacing a local:// row with canonical https URL, delete old row first when needed.
            if event.source_pdf_url != url:
                conn.execute("DELETE FROM auction_lots WHERE auction_event_id = ?", (eid,))
                conn.execute("DELETE FROM auction_events WHERE id = ?", (eid,))
            event_id = db.upsert_auction_event(event)
            for lot in lots:
                lot.auction_event_id = event_id
            db.insert_auction_lots(event_id, lots)
            logger.info(
                "Reparsed %s as PVRM event_id=%s lots=%s date=%s",
                _filename(url),
                event_id,
                len(lots),
                auction_date,
            )


def main() -> None:
    db.init_db()
    n_dates = backfill_dates()
    n_dupes = remove_local_duplicates()
    fix_misclassified_pvrm()
    with db.get_connection() as conn:
        events = conn.execute("SELECT COUNT(*) FROM auction_events").fetchone()[0]
        lots = conn.execute("SELECT COUNT(*) FROM auction_lots").fetchone()[0]
        null_dates = conn.execute(
            "SELECT COUNT(*) FROM auction_events WHERE auction_date IS NULL OR auction_date=''"
        ).fetchone()[0]
        by_cat = conn.execute(
            "SELECT category, COUNT(*) FROM auction_events GROUP BY category"
        ).fetchall()
    logger.info(
        "DONE dates_fixed=%s local_dupes_removed=%s events=%s lots=%s null_dates=%s by_cat=%s",
        n_dates,
        n_dupes,
        events,
        lots,
        null_dates,
        by_cat,
    )


if __name__ == "__main__":
    main()
