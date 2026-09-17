"""Full scrape: index PDFs first, then optional TVRM template probing.

Resumable via SQLite (skips URLs already stored with lots, unless --force).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from car_auction import db
from car_auction.discovery.pvrm_index import DiscoveredPDF
from car_auction.pipeline import run_discovery, run_download_and_parse


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "data/processed/full_scrape.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("full_scrape")


def already_stored_urls() -> set[str]:
    db.init_db()
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.source_pdf_url
            FROM auction_events e
            JOIN auction_lots l ON l.auction_event_id = e.id
            GROUP BY e.source_pdf_url
            HAVING COUNT(l.id) > 0
            """
        ).fetchall()
    return {r[0] for r in rows}


def summarize() -> None:
    with db.get_connection() as conn:
        events = conn.execute("SELECT COUNT(*) FROM auction_events").fetchone()[0]
        lots = conn.execute("SELECT COUNT(*) FROM auction_lots").fetchone()[0]
        by_cat = conn.execute(
            "SELECT category, COUNT(*) FROM auction_events GROUP BY category"
        ).fetchall()
        dated = conn.execute(
            "SELECT COUNT(*) FROM auction_events WHERE auction_date IS NOT NULL"
        ).fetchone()[0]
        empty = conn.execute(
            """
            SELECT COUNT(*) FROM auction_events e
            WHERE NOT EXISTS (
              SELECT 1 FROM auction_lots l WHERE l.auction_event_id = e.id
            )
            """
        ).fetchone()[0]
    logger.info(
        "DB summary: events=%s lots=%s by_cat=%s dated=%s empty_events=%s",
        events,
        lots,
        by_cat,
        dated,
        empty,
    )


def batch_run(pdfs: list[DiscoveredPDF], batch_size: int = 10) -> None:
    total = len(pdfs)
    for i in range(0, total, batch_size):
        batch = pdfs[i : i + batch_size]
        logger.info("Processing batch %s-%s / %s", i + 1, i + len(batch), total)
        t0 = time.time()
        try:
            run_download_and_parse(batch)
        except Exception:
            logger.exception("Batch failed; continuing one-by-one")
            for pdf in batch:
                try:
                    run_download_and_parse([pdf])
                except Exception:
                    logger.exception("Failed PDF: %s", pdf.url)
        logger.info("Batch done in %.1fs", time.time() - t0)
        summarize()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-templates", action="store_true")
    ap.add_argument("--templates-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="Re-parse even if URL already stored")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=5)
    args = ap.parse_args()

    db.init_db()
    done = set() if args.force else already_stored_urls()
    logger.info("Already stored URLs with lots: %s", len(done))

    pdfs: list[DiscoveredPDF] = []
    if not args.templates_only:
        logger.info("Discovering index PDFs...")
        index_pdfs = run_discovery(include_templates=False)
        logger.info("Index discovered: %s", len(index_pdfs))
        pdfs.extend(index_pdfs)

    if args.include_templates or args.templates_only:
        logger.info("Discovering template PDFs (slow)...")
        from car_auction.discovery import discover_tvrm_pdfs_from_templates

        tmpl = list(discover_tvrm_pdfs_from_templates())
        logger.info("Template discovered: %s", len(tmpl))
        pdfs.extend(tmpl)

    # de-dupe by url
    uniq = {p.url: p for p in pdfs}
    pdfs = list(uniq.values())
    if not args.force:
        pdfs = [p for p in pdfs if p.url not in done]
    if args.limit is not None:
        pdfs = pdfs[: args.limit]

    logger.info("Queued for download/parse: %s", len(pdfs))
    batch_run(pdfs, batch_size=args.batch_size)
    summarize()
    logger.info("Scrape finished")


if __name__ == "__main__":
    main()
