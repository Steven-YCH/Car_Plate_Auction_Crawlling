"""Parse discovered TVRM template URLs into the DB (skips already-stored)."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from car_auction import db
from car_auction.discovery.pvrm_index import DiscoveredPDF
from car_auction.pipeline import run_download_and_parse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "data/processed/template_scrape.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("tmpl_scrape")


def already_stored() -> set[str]:
    db.init_db()
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.source_pdf_url FROM auction_events e
            JOIN auction_lots l ON l.auction_event_id = e.id
            GROUP BY e.source_pdf_url HAVING COUNT(l.id) > 0
            """
        ).fetchall()
    return {r[0] for r in rows}


def main() -> None:
    path = ROOT / "data/processed/tvrm_template_urls.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    done = already_stored()
    pdfs = []
    for item in raw:
        if item["url"] in done:
            continue
        pdfs.append(
            DiscoveredPDF(
                category=item.get("category", "TVRM"),
                url=item["url"],
                label=item.get("label", item["url"]),
                source_page=item.get("source_page", "template"),
            )
        )
    logger.info("Template URLs total=%s queued=%s already=%s", len(raw), len(pdfs), len(raw) - len(pdfs))
    for i, pdf in enumerate(pdfs, 1):
        logger.info("[%s/%s] %s", i, len(pdfs), pdf.url)
        try:
            run_download_and_parse([pdf])
        except Exception:
            logger.exception("Failed %s", pdf.url)
        if i % 5 == 0:
            with db.get_connection() as conn:
                logger.info(
                    "progress events=%s lots=%s",
                    conn.execute("select count(*) from auction_events").fetchone()[0],
                    conn.execute("select count(*) from auction_lots").fetchone()[0],
                )
    with db.get_connection() as conn:
        logger.info(
            "DONE events=%s lots=%s by_cat=%s",
            conn.execute("select count(*) from auction_events").fetchone()[0],
            conn.execute("select count(*) from auction_lots").fetchone()[0],
            conn.execute("select category, count(*) from auction_events group by category").fetchall(),
        )


if __name__ == "__main__":
    main()
