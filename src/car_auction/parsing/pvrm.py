"""Parsing logic for PVRM auction PDFs.

Initial implementation is conservative and may need refinement using
real sample PDFs. It uses PyMuPDF to extract text and relies on simple
regular-expression patterns.
"""

from __future__ import annotations

import re
from typing import Optional, List, Tuple

import fitz  # PyMuPDF
import pandas as pd

from ..config import parsing as parsing_cfg
from ..ocr import extract_ocr_items, extract_text_lines_with_fallback, ocr_extract_lines
from .amounts import is_amount_or_unsold, normalize_amount_token
from .base import df_to_lots, validate_auction_df


# Amount lines in PVRM PDFs are typically standalone numbers with thousands
# separators, e.g. "5,000", "50,000", "250,000" or with an "@" prefix
# (unsold: special fee $5,000) or a leading "$". Critically, they always
# contain at least one comma (or OCR dot-thousands), whereas row-layout
# fragments like "98", "1", "666" do not.
AMOUNT_LINE_RE = re.compile(r"^@?\$?\s*[0-9]{1,3}(?:[.,][0-9]{3})+(?:\.\d+)?\s*$")


def _looks_like_amount_line(line: str) -> bool:
    """Return True if a line is a standalone amount like "5,000" or "@5,000"."""

    line = normalize_amount_token(line)
    if not line:
        return False
    return bool(AMOUNT_LINE_RE.match(line))


def _is_summary_amount(prev_line: Optional[str], amount_line: str) -> bool:
    """Heuristically identify the grand total line (e.g. "$1,938,000").

    We skip this so it is not mis-assigned as the auction amount of the last
    plate in the document.
    """

    if prev_line is None:
        return False

    prev_lower = prev_line.lower()
    if "total sale proceeds" in prev_lower or "拍賣所得款項" in prev_lower:
        return True

    # Be conservative: also ignore amounts where the previous line mentions a
    # "session" – these are almost certainly summary lines.
    if "session" in prev_lower:
        return True

    return False


def _is_candidate_mark_line(line: str) -> bool:
    """Return True if a line looks like a plate label rather than prose.

    In the TD PVRM PDFs, each plate group appears as 1–3 label lines followed
    by one amount line. The first label line is the full mark (e.g. "B0SS L",
    "K FAM1LY(n/a)", "PT1PT1"). The subsequent label lines show how it is
    broken across one or two rows, e.g.::

        B0SS L
        B0SS
        L
        50,000

    We treat lines that are all ASCII upper-case letters / digits / spaces
    (after stripping the optional "(n/a)" notice) as potential mark lines.
    This filters out English/Chinese prose and headings which contain
    lowercase letters or punctuation.
    """

    txt = line.strip()
    if not txt:
        return False

    # Remove the (n/a) note – it is not part of the mark string.
    txt_clean = re.sub(r"\(n/a\)", "", txt, flags=re.IGNORECASE).strip()
    if not txt_clean:
        return False

    # Exclude obvious non-mark lines.
    if any(ch.islower() for ch in txt_clean):
        return False
    if any(ord(ch) > 127 for ch in txt_clean):
        # Non-ASCII characters (Chinese text, punctuation, etc.)
        # are strong indicators of headings / prose rather than marks.
        return False
    if any(ch in txt_clean for ch in ",:@$"):
        # Commas / colons / @ / $ usually indicate prose or amounts.
        return False

    # Must contain at least one alphanumeric character.
    if not any(ch.isalnum() for ch in txt_clean):
        return False

    lower = txt_clean.lower()
    header_keywords = [
        "result of auction",
        "auction of personalized",
        "held on",
        "單行排列",
        "雙行排列",
        "in 1 row",
        "in 2 rows",
        "session",
        "total sale proceeds",
    ]
    if any(kw in lower for kw in header_keywords):
        return False

    return True


def _extract_mark_from_group(group_lines: List[str]) -> Optional[str]:
    """Derive the best LPN string from a group of label lines.

    We gather all lines that look like marks and choose the longest one,
    because for multi-row marks the top line contains the full mark while
    subsequent lines contain partial fragments (e.g. "B0SS L" vs. "B0SS" or
    "SUN666" vs. "SUN").
    """

    candidates: List[str] = []
    for ln in group_lines:
        if not _is_candidate_mark_line(ln):
            continue
        cleaned = re.sub(r"\(n/a\)", "", ln, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)  # normalise spaces
        if cleaned:
            candidates.append(cleaned)

    if not candidates:
        return None

    # Pick the longest candidate; this tends to be the full mark.
    mark = max(candidates, key=len)
    return mark


def _parse_amount(amount_line: str) -> Optional[int]:
    """Parse an amount line like "5,000" or "@5,000" into an integer."""

    s = normalize_amount_token(amount_line)
    s = s.lstrip("@$ ").replace(",", "").strip()
    if not s or not s.replace(".", "", 1).isdigit():
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _records_from_lines(lines: List[str]) -> List[dict]:
    groups: List[Tuple[List[str], str]] = []
    current_group: List[str] = []
    prev_nonempty: Optional[str] = None

    for ln in lines:
        if ln == "---COL---":
            current_group = []
            prev_nonempty = None
            continue
        if _looks_like_amount_line(ln):
            if _is_summary_amount(prev_nonempty, ln):
                current_group = []
                prev_nonempty = ln
                continue
            if current_group:
                groups.append((current_group.copy(), ln))
                current_group = []
        else:
            current_group.append(ln)
        prev_nonempty = ln

    records: List[dict] = []
    for label_lines, amount_line in groups:
        mark = _extract_mark_from_group(label_lines)
        if not mark:
            continue
        amount = _parse_amount(amount_line)
        if amount is None:
            continue
        records.append({"LPN": mark, "Auction_Amount": amount})
    return records


def _column_centers(xs: List[float], expected: int = 4) -> List[float]:
    if len(xs) < max(2, expected):
        return []
    xs = sorted(xs)
    gaps = [(xs[i + 1] - xs[i], i) for i in range(len(xs) - 1)]
    gaps.sort(reverse=True)
    split = sorted(i for g, i in gaps[: expected - 1] if g > 40)
    bounds = [0] + [i + 1 for i in split] + [len(xs)]
    centers: List[float] = []
    for a, b in zip(bounds, bounds[1:]):
        chunk = xs[a:b]
        if chunk:
            centers.append(sum(chunk) / len(chunk))
    return sorted(centers)


def _dedupe_ocr_items(items: List[dict]) -> List[dict]:
    items = sorted(items, key=lambda it: (it["cy"], it["cx"]))
    kept: List[dict] = []
    for it in items:
        if any(
            it["text"] == k["text"]
            and abs(it["cx"] - k["cx"]) < 10
            and abs(it["cy"] - k["cy"]) < 10
            for k in kept
        ):
            continue
        kept.append(it)
    return kept


def _records_from_ocr_items_one_page(items: List[dict]) -> List[dict]:
    kept = _dedupe_ocr_items(items)
    amount_xs = [it["cx"] for it in kept if is_amount_or_unsold(it["text"])]
    centers = _column_centers(amount_xs, expected=4)
    if not centers:
        return _records_from_lines([it["text"] for it in kept])

    cols: dict[int, list] = {i: [] for i in range(len(centers))}
    for it in kept:
        c = min(range(len(centers)), key=lambda i: abs(it["cx"] - centers[i]))
        cols[c].append(it)

    lines: List[str] = []
    for i in sorted(cols):
        for it in sorted(cols[i], key=lambda z: z["cy"]):
            lines.append(it["text"])
        lines.append("---COL---")
    return _records_from_lines(lines)


def _records_from_ocr_columns(doc: fitz.Document) -> List[dict]:
    """OCR + per-page column-major reading order for old PVRM handouts.

    Important: OCR coordinates reset every page, so pages must be parsed
    separately or rows from different pages get interleaved.
    """

    from ..ocr import OCRConfig, _ensure_ocr
    import numpy as np

    cfg = OCRConfig()
    engine_name, engine = _ensure_ocr(cfg.engine)
    records: List[dict] = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(cfg.zoom, cfg.zoom))
        items: List[dict] = []
        if engine_name == "rapid":
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:
                arr = arr[:, :, :3]
            result, _elapse = engine(arr)
            for entry in result or []:
                box, text, score = entry[0], entry[1], entry[2]
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                t = (text or "").strip()
                if not t:
                    continue
                items.append(
                    {
                        "cx": sum(xs) / 4.0,
                        "cy": sum(ys) / 4.0,
                        "text": t,
                        "score": score,
                    }
                )
        else:
            result = engine.ocr(pix.tobytes("png"))
            for line in result or []:
                if not line:
                    continue
                try:
                    box, (text, score) = line[0], line[1]
                except Exception:
                    continue
                t = (text or "").strip()
                if not t:
                    continue
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                items.append(
                    {
                        "cx": sum(xs) / 4.0,
                        "cy": sum(ys) / 4.0,
                        "text": t,
                        "score": score,
                    }
                )

        records.extend(_records_from_ocr_items_one_page(items))

    return records


def parse_pvrm_pdf(path: str):
    """Parse a PVRM auction PDF into a list of AuctionLot objects.

    Modern handouts: native PDF text, mark-group + amount lines.
    Older multi-column handouts: amounts are often glyph-split or only
    recoverable via OCR; we then parse column-by-column.
    """

    doc = fitz.open(path)
    native_lines: List[str] = extract_text_lines_with_fallback(doc)
    native_has_amounts = any(_looks_like_amount_line(ln) for ln in native_lines)

    records = _records_from_lines(native_lines) if native_has_amounts else []

    # Old PVRMs / weak extractions: prefer column-aware OCR when enabled.
    if parsing_cfg.use_ocr_fallback and (not native_has_amounts or len(records) < 20):
        ocr_records = _records_from_ocr_columns(doc)
        if len(ocr_records) > len(records):
            records = ocr_records
        elif not records:
            # last resort: flat OCR reading order
            records = _records_from_lines(ocr_extract_lines(doc))

    df = pd.DataFrame.from_records(records)
    if not validate_auction_df(df):
        return None
    return df_to_lots(df)






