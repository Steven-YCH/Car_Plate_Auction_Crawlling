"""Simple CLI entrypoint for the car_auction package."""

from __future__ import annotations

import argparse
import csv
from typing import List

from . import db
from .config import paths
from .pipeline import run_discovery, run_download_and_parse


def cmd_discover(args: argparse.Namespace) -> None:
    pdfs = run_discovery(include_templates=args.include_templates)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]
    print(f"Discovered {len(pdfs)} PDFs")
    for pdf in pdfs:
        print(f"[{pdf.category}] {pdf.url}  (from {pdf.source_page})")


def cmd_download(args: argparse.Namespace) -> None:
    pdfs = run_discovery(include_templates=args.include_templates)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]
    run_download_and_parse(pdfs)


def cmd_export(args: argparse.Namespace) -> None:
    db.init_db()
    out_path = args.out or paths.processed + "/auction_lots.csv"

    from .db import get_connection

    rows = []
    header = [
        "auction_event_id",
        "category",
        "auction_date",
        "source_pdf_url",
        "lpn",
        "auction_amount",
        "currency",
        "lot_number",
        "remarks",
    ]
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                e.id,
                e.category,
                e.auction_date,
                e.source_pdf_url,
                l.lpn,
                l.auction_amount,
                l.currency,
                l.lot_number,
                l.remarks
            FROM auction_lots l
            JOIN auction_events e ON l.auction_event_id = e.id
            ORDER BY e.auction_date, e.id
            """
        )
        rows = cur.fetchall()

    if out_path.lower().endswith(".xlsx"):
        import pandas as pd

        df = pd.DataFrame(rows, columns=header)
        df.to_excel(out_path, index=False)
    else:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    print(f"Exported {len(rows)} auction lots to {out_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Car license auction result crawler")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="List discovered auction result PDFs")
    p_discover.add_argument(
        "--include-templates",
        action="store_true",
        help="Include slow date-template probes for TVRM legacy PDFs",
    )
    p_discover.add_argument(
        "--limit",
        type=int,
        help="Limit the number of discovered PDFs printed (for quick tests)",
    )
    p_discover.set_defaults(func=cmd_discover)

    p_download = sub.add_parser(
        "download", help="Discover, download, parse and store auction results"
    )
    p_download.add_argument(
        "--include-templates",
        action="store_true",
        help="Include slow date-template probes for TVRM legacy PDFs",
    )
    p_download.add_argument(
        "--limit",
        type=int,
        help="Limit the number of PDFs to download/parse (for quick tests)",
    )
    p_download.set_defaults(func=cmd_download)

    p_export = sub.add_parser("export", help="Export consolidated auction lots to CSV or XLSX")
    p_export.add_argument("--out", type=str, help="Output CSV/XLSX path")
    p_export.set_defaults(func=cmd_export)

    return parser


def main(argv: List[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
