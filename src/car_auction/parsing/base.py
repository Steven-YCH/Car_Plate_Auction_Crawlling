"""Shared utilities and validation helpers for parsing."""

from __future__ import annotations

from typing import Iterable, List

import pandas as pd

from ..models import AuctionLot


def validate_auction_df(df: pd.DataFrame) -> bool:
    """Basic sanity checks on a parsed auction table.

    This can be extended with more domain-specific rules.
    """

    required_columns = {"lpn", "auction_amount"}
    if not required_columns.issubset({c.lower() for c in df.columns}):
        return False

    if len(df) == 0:
        return False

    return True


def df_to_lots(df: pd.DataFrame) -> List[AuctionLot]:
    """Convert a validated DataFrame into AuctionLot objects."""

    # Normalise column names
    cols = {c.lower(): c for c in df.columns}
    lpn_col = cols.get("lpn") or cols.get("registration mark") or cols.get("vrm")
    amt_col = cols.get("auction_amount") or cols.get("amount")

    lots: List[AuctionLot] = []
    for _, row in df.iterrows():
        lpn = str(row[lpn_col]).strip()
        amt_val = row[amt_col]
        try:
            amount = int(str(amt_val).replace(",", "")) if pd.notna(amt_val) else None
        except ValueError:
            amount = None

        lots.append(
            AuctionLot(
                id=None,
                auction_event_id=None,
                lpn=lpn,
                auction_amount=amount,
            )
        )
    return lots


