"""Amount helpers shared by parsers."""

from __future__ import annotations

import re
from typing import Optional, Tuple

AMOUNT_RE = re.compile(r"^@?\$?\s*[0-9]{1,3}(?:[.,][0-9]{3})+(?:\.\d+)?$")
US_RE = re.compile(r"^(U/?S|S/n)$", re.I)


def normalize_amount_token(token: str) -> str:
    token = token.strip()
    # OCR sometimes uses dot as thousands separator: 3.000 -> 3,000
    if re.match(r"^\d{1,3}\.\d{3}$", token):
        token = token.replace(".", ",")
    return token


def parse_amount_token(token: str) -> Tuple[Optional[int], Optional[str]]:
    """Return (amount, remarks). remarks is U/S or special_fee when applicable."""

    token = normalize_amount_token(token)
    if not token:
        return None, None
    if US_RE.match(token):
        return None, "U/S"
    if AMOUNT_RE.match(token) or (
        token.startswith("@") and any(ch.isdigit() for ch in token)
    ):
        remarks = "special_fee" if token.lstrip().startswith("@") else None
        digits = re.sub(r"[^0-9]", "", token.lstrip("@$ "))
        if not digits:
            return None, None
        return int(digits), remarks
    return None, None


def is_amount_or_unsold(token: str) -> bool:
    amount, remarks = parse_amount_token(token)
    return remarks == "U/S" or amount is not None
