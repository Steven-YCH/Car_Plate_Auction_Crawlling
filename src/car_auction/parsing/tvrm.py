"""Parsing logic for Traditional VRM (TVRM) auction PDFs.

Modern TD TVRM handouts expose clean text as repeating triples:

    PREFIX
    NUMBER
    AMOUNT | U/S | @AMOUNT

Some lines combine prefix+number (\"WW 765\"). Older PDFs often use fonts
without usable ToUnicode maps; those fall back to OCR and a row-wise
spatial parse (prefix, number, amount across each horizontal lot cell).
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

import fitz

from ..config import parsing as parsing_cfg
from ..ocr import extract_ocr_items, text_looks_garbled
from ..models import AuctionLot
from .amounts import is_amount_or_unsold, parse_amount_token
from .base import df_to_lots, validate_auction_df

import pandas as pd

PREFIX_RE = re.compile(r"^\*?[A-Z]{1,2}$")
NUM_RE = re.compile(r"^\d{1,4}$")
COMBINED_RE = re.compile(r"^\*?([A-Z]{1,2})\s+(\d{1,4})$")
NOISE = {"*", "$", "PP", "S", "n"}


def _parse_tvrm_tokens(tokens: Sequence[str]) -> List[Tuple[str, Optional[int], Optional[str]]]:
    lots: List[Tuple[str, Optional[int], Optional[str]]] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i].strip()
        if not tok or tok in NOISE:
            i += 1
            continue

        m = COMBINED_RE.match(tok)
        if m and i + 1 < n and is_amount_or_unsold(tokens[i + 1]):
            amount, remarks = parse_amount_token(tokens[i + 1])
            lots.append((f"{m.group(1)} {m.group(2)}", amount, remarks))
            i += 2
            continue

        if PREFIX_RE.match(tok) and i + 1 < n and NUM_RE.match(tokens[i + 1].strip()):
            prefix = tok.lstrip("*")
            num = tokens[i + 1].strip()
            if i + 2 < n and is_amount_or_unsold(tokens[i + 2]):
                amount, remarks = parse_amount_token(tokens[i + 2])
                lots.append((f"{prefix} {num}", amount, remarks))
                i += 3
                continue
            i += 1
            continue

        i += 1
    return lots


def _parse_from_text_lines(lines: Sequence[str]) -> List[Tuple[str, Optional[int], Optional[str]]]:
    return _parse_tvrm_tokens(lines)


def _parse_from_ocr_items(
    items: Sequence[dict],
) -> List[Tuple[str, Optional[int], Optional[str]]]:
    """Parse OCR boxes using row-wise horizontal triples.

    Legacy handouts place each lot as PREFIX / NUMBER / AMOUNT on one row,
    with several lots across the page.
    """

    if not items:
        return []

    # Bucket into rows by cy.
    items_sorted = sorted(items, key=lambda it: (round(it["cy"] / 12) * 12, it["cx"]))
    rows: list[list[dict]] = []
    for it in items_sorted:
        if not rows:
            rows.append([it])
            continue
        if abs(it["cy"] - rows[-1][0]["cy"]) <= 14:
            rows[-1].append(it)
        else:
            rows.append([it])

    lots: List[Tuple[str, Optional[int], Optional[str]]] = []
    for row in rows:
        row_sorted = sorted(row, key=lambda it: it["cx"])
        tokens = [it["text"] for it in row_sorted]
        # Skip header-ish rows
        joined = " ".join(tokens).lower()
        if "result of auction" in joined or "held on" in joined:
            continue
        lots.extend(_parse_tvrm_tokens(tokens))
    return lots


def _to_lots(
    records: List[Tuple[str, Optional[int], Optional[str]]]
) -> Optional[List[AuctionLot]]:
    if not records:
        return None
    rows = [
        {"LPN": lpn, "Auction_Amount": amount if amount is not None else 0, "remarks": remarks}
        for lpn, amount, remarks in records
    ]
    df = pd.DataFrame.from_records(rows)
    # validate requires non-empty lpn/amount columns; keep zero for U/S then fix
    if not validate_auction_df(df):
        return None
    lots = df_to_lots(df)
    for lot, (_, amount, remarks) in zip(lots, records):
        lot.auction_amount = amount
        lot.remarks = remarks
    return lots


def parse_tvrm_pdf(path: str) -> Optional[List[AuctionLot]]:
    """Parse a TVRM auction PDF into AuctionLot objects."""

    doc = fitz.open(path)
    lines = []
    for i, page in enumerate(doc):
        if parsing_cfg.max_pages is not None and i >= parsing_cfg.max_pages:
            break
        for raw in page.get_text().splitlines():
            ln = raw.strip()
            if ln:
                lines.append(ln)

    records: List[Tuple[str, Optional[int], Optional[str]]] = []
    if lines and not text_looks_garbled(lines):
        records = _parse_from_text_lines(lines)
    elif parsing_cfg.use_ocr_fallback:
        items = extract_ocr_items(doc)
        records = _parse_from_ocr_items(items)
    else:
        # Last resort: still try native lines even if garbled.
        records = _parse_from_text_lines(lines)

    # If text path yielded nothing and OCR is enabled, try OCR anyway.
    if not records and parsing_cfg.use_ocr_fallback:
        items = extract_ocr_items(doc)
        records = _parse_from_ocr_items(items)

    return _to_lots(records)
