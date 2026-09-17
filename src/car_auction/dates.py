"""Infer auction dates from filenames, URLs, labels, and PDF text."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable, Optional
from urllib.parse import unquote


_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 20101219 / 20250517 / aucr05_20191222183029 (date may be followed by time digits)
    (re.compile(r"(?<!\d)((?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))(?:\d{0,6})?(?!\d)"), "%Y%m%d"),
    # 2010-12-19 / 2010.12.19
    (re.compile(r"(?<!\d)(19|20)\d{2}[-.](0[1-9]|1[0-2])[-.](0[1-9]|[12]\d|3[01])(?!\d)"), "%Y-%m-%d"),
    # 05-06-2011 / 1-5-2011 / 05.06.2011
    (re.compile(r"(?<!\d)(\d{1,2})[-.](\d{1,2})[-.]((?:19|20)\d{2})(?!\d)"), "%d-%m-%Y"),
    # 03_09_2022
    (re.compile(r"(?<!\d)(\d{1,2})_(\d{1,2})_((?:19|20)\d{2})(?!\d)"), "%d_%m_%Y"),
    # 18 May 2025 / 05 June 2011
    (
        re.compile(
            r"(?<!\d)(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+((?:19|20)\d{2})",
            re.I,
        ),
        "%d %b %Y",
    ),
    # 12dec2010 / 12Dec2010 (no separators)
    (
        re.compile(
            r"(?<!\d)(\d{1,2})(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"((?:19|20)\d{2})",
            re.I,
        ),
        "%d%b%Y",
    ),
]

_CHINESE_DATE_RE = re.compile(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_PAREN_YYMMDD_RE = re.compile(r"\((\d{2})(\d{2})(\d{2})\)")


def _try_parse(raw: str, fmt: str) -> Optional[date]:
    raw = raw.replace(".", "-")
    # Normalise full month names to abbreviated for %b
    if "%b" in fmt:
        cleaned = raw.title().replace("Sept", "Sep")
        if fmt == "%d%b%Y":
            # Insert separators for strptime, e.g. 12Dec2010 -> 12 Dec 2010
            m = re.match(
                r"(\d{1,2})([A-Za-z]+)((?:19|20)\d{2})$",
                cleaned.replace(" ", ""),
            )
            if m:
                cleaned = f"{m.group(1)} {m.group(2)} {m.group(3)}"
            try:
                return datetime.strptime(cleaned, "%d %B %Y").date()
            except ValueError:
                pass
            try:
                return datetime.strptime(cleaned, "%d %b %Y").date()
            except ValueError:
                return None
        try:
            return datetime.strptime(cleaned.replace("Sept ", "Sep "), "%d %B %Y").date()
        except ValueError:
            pass
        try:
            return datetime.strptime(cleaned.replace("Sept ", "Sep "), "%d %b %Y").date()
        except ValueError:
            return None
    try:
        return datetime.strptime(raw, fmt).date()
    except ValueError:
        # day/month without zero padding already covered by %-? not on Windows; try flexible
        if fmt == "%d-%m-%Y":
            parts = re.split(r"[-.]", raw)
            if len(parts) == 3:
                try:
                    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    return date(y, m, d)
                except ValueError:
                    return None
        if fmt == "%d_%m_%Y":
            parts = raw.split("_")
            if len(parts) == 3:
                try:
                    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    return date(y, m, d)
                except ValueError:
                    return None
        return None


def extract_date_from_text(text: str) -> Optional[date]:
    """Best-effort date extraction from a filename, URL, label, or PDF header line."""

    if not text:
        return None
    text = unquote(text)

    # Chinese labels from TD index pages, e.g. 2007年5月5日
    m = _CHINESE_DATE_RE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Prefer explicit English auction titles when present.
    m = re.search(
        r"Held on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text,
        flags=re.I,
    )
    if m:
        parsed = _try_parse(m.group(1), "%d %b %Y")
        if parsed:
            return parsed

    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        # Prefer the first capture group when present (e.g. YYYYMMDD without trailing time).
        raw = m.group(1) if (m.lastindex and fmt == "%Y%m%d") else m.group(0)
        if fmt == "%Y-%m-%d":
            raw = raw.replace(".", "-")
        parsed = _try_parse(raw, fmt)
        if parsed:
            return parsed

    # Legacy compact filenames like auction result handout (070505).pdf -> 2007-05-05
    m = _PAREN_YYMMDD_RE.search(text)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + yy if yy < 70 else 1900 + yy
        try:
            return date(year, mm, dd)
        except ValueError:
            pass
    return None


def extract_date_from_candidates(candidates: Iterable[str]) -> Optional[date]:
    for c in candidates:
        d = extract_date_from_text(c)
        if d:
            return d
    return None
