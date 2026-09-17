"""Very small SQLite persistence layer.

We keep this intentionally simple: no ORM, just a few helper functions
wrapping `sqlite3` and operating on the dataclasses in ``models``.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Tuple

from .config import paths
from .models import AuctionEvent, AuctionLot


@contextmanager
def get_connection():
    conn = sqlite3.connect(paths.db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't already exist."""

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auction_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                auction_date TEXT,
                source_pdf_url TEXT NOT NULL UNIQUE,
                source_pdf_filename TEXT NOT NULL,
                source_pdf_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auction_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auction_event_id INTEGER NOT NULL,
                lpn TEXT NOT NULL,
                auction_amount INTEGER,
                currency TEXT,
                lot_number TEXT,
                remarks TEXT,
                FOREIGN KEY (auction_event_id) REFERENCES auction_events(id)
            )
            """
        )


def upsert_auction_event(event: AuctionEvent) -> int:
    """Insert or update an AuctionEvent and return its database ID.

    Uniqueness is determined by ``source_pdf_url``.
    """

    with get_connection() as conn:
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        auction_date_str = event.auction_date.isoformat() if event.auction_date else None

        cur.execute(
            """
            INSERT INTO auction_events (
                category, auction_date, source_pdf_url, source_pdf_filename,
                source_pdf_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_pdf_url) DO UPDATE SET
                category=excluded.category,
                auction_date=excluded.auction_date,
                source_pdf_filename=excluded.source_pdf_filename,
                source_pdf_hash=excluded.source_pdf_hash,
                updated_at=excluded.updated_at
            """,
            (
                event.category,
                auction_date_str,
                event.source_pdf_url,
                event.source_pdf_filename,
                event.source_pdf_hash,
                now,
                now,
            ),
        )
        return cur.lastrowid or cur.execute(
            "SELECT id FROM auction_events WHERE source_pdf_url = ?",
            (event.source_pdf_url,),
        ).fetchone()[0]


def insert_auction_lots(event_id: int, lots: Iterable[AuctionLot]) -> None:
    """Bulk insert lots for a given event, replacing any existing ones."""

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM auction_lots WHERE auction_event_id = ?", (event_id,))

        rows: Iterable[Tuple] = (
            (
                event_id,
                lot.lpn,
                lot.auction_amount,
                lot.currency,
                lot.lot_number,
                lot.remarks,
            )
            for lot in lots
        )

        cur.executemany(
            """
            INSERT INTO auction_lots (
                auction_event_id, lpn, auction_amount, currency, lot_number, remarks
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            list(rows),
        )


