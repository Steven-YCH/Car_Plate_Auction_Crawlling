"""Core domain models (dataclasses) for auction results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class AuctionEvent:
    id: Optional[int]
    category: str  # "PVRM" or "TVRM"
    auction_date: Optional[date]
    source_pdf_url: str
    source_pdf_filename: str
    source_pdf_hash: Optional[str] = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class AuctionLot:
    id: Optional[int]
    auction_event_id: Optional[int]
    lpn: str
    auction_amount: Optional[int]
    currency: str = "HKD"
    lot_number: Optional[str] = None
    remarks: Optional[str] = None
