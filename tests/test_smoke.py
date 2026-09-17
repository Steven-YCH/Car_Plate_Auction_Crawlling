"""Small runnable checks for restored package functionality."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from car_auction.dates import extract_date_from_text
from car_auction.parsing.amounts import is_amount_or_unsold, parse_amount_token
from car_auction.parsing.tvrm import _parse_tvrm_tokens


def test_dates():
    assert extract_date_from_text("tvrm_auction_result_20250517_chi.pdf") == date(2025, 5, 17)
    assert extract_date_from_text("aucr05_20191222183029.pdf") == date(2019, 12, 22)
    assert extract_date_from_text("auction result handout 05-06-2011.pdf") == date(2011, 6, 5)
    assert extract_date_from_text("Held on 18 May 2025") == date(2025, 5, 18)
    assert extract_date_from_text("tvrm auction result 1-5-2011.pdf") == date(2011, 5, 1)


def test_amounts():
    assert parse_amount_token("5,000") == (5000, None)
    assert parse_amount_token("@1,000") == (1000, "special_fee")
    assert parse_amount_token("U/S") == (None, "U/S")
    assert parse_amount_token("3.000") == (3000, None)
    assert is_amount_or_unsold("U/S")
    assert is_amount_or_unsold("7,000")


def test_tvrm_token_triples():
    tokens = [
        "KY",
        "727",
        "U/S",
        "FU",
        "64",
        "7,000",
        "ST",
        "675",
        "@1,000",
        "WW 765",
        "3,000",
    ]
    lots = _parse_tvrm_tokens(tokens)
    assert lots[0] == ("KY 727", None, "U/S")
    assert lots[1] == ("FU 64", 7000, None)
    assert lots[2] == ("ST 675", 1000, "special_fee")
    assert lots[3] == ("WW 765", 3000, None)


def test_parse_local_samples_if_present():
    pvrm = ROOT / "data/raw/pvrm/PVRMs%20Auction%20Result%20Handout%2018%20May%202025.Chin.pdf"
    tvrm = ROOT / "data/raw/tvrm/tvrm_auction_result_20250517_chi.pdf"
    if not pvrm.exists() or not tvrm.exists():
        return
    from car_auction.parsing import parse_pvrm_pdf, parse_tvrm_pdf

    pvrm_lots = parse_pvrm_pdf(str(pvrm))
    tvrm_lots = parse_tvrm_pdf(str(tvrm))
    assert pvrm_lots and len(pvrm_lots) >= 50
    assert tvrm_lots and len(tvrm_lots) >= 50


if __name__ == "__main__":
    test_dates()
    test_amounts()
    test_tvrm_token_triples()
    test_parse_local_samples_if_present()
    print("ok")
