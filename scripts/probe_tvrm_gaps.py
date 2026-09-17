"""Targeted TVRM URL probe for sparse years (weekends + known templates)."""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/tvrm_gap_probe.json"
MERGED = ROOT / "data/processed/tvrm_template_urls.json"


def daterange(start: date, end: date, weekdays=()):
    d = end
    while d >= start:
        if not weekdays or d.weekday() in weekdays:
            yield d
        d -= timedelta(days=1)


def main() -> None:
    s = requests.Session()
    found = []
    t0 = time.time()

    # Focus on historically sparse TVRM years.
    years = [2014, 2015, 2016, 2017, 2018, 2020]
    templates = [
        (
            "auction-result-handout",
            "https://www.td.gov.hk/filemanager/common/auction-result-handout_{}.pdf",
            "%Y%m%d",
            (5, 6),  # Sat/Sun
        ),
        (
            "handout_ddmm",
            "https://www.td.gov.hk/filemanager/common/auction%20result%20handout%20{}.pdf",
            "%d-%m-%Y",
            (5, 6),
        ),
        (
            "results_handout",
            "https://www.td.gov.hk/filemanager/common/auction%20results%20handout_{}.pdf",
            "%Y%m%d",
            (5, 6),
        ),
        (
            "tvrm_results_handout",
            "https://www.td.gov.hk/filemanager/common/tvrm%20auction%20results%20handout_{}.pdf",
            "%Y%m%d",
            (5, 6),
        ),
        (
            "chi",
            "https://www.td.gov.hk/filemanager/tc/content_4804/tvrm_auction_result_{}_chi.pdf",
            "%Y%m%d",
            (),
        ),
        (
            "plain4804",
            "https://www.td.gov.hk/filemanager/tc/content_4804/tvrm_auction_result_{}.pdf",
            "%Y%m%d",
            (),
        ),
    ]

    existing = set()
    if MERGED.exists():
        existing = {x["url"] for x in json.loads(MERGED.read_text(encoding="utf-8"))}

    for year in years:
        start, end = date(year, 1, 1), date(year, 12, 31)
        for name, tmpl, fmt, weekdays in templates:
            hits = 0
            fail = 0
            for d in daterange(start, end, weekdays):
                ds = d.strftime(fmt)
                url = tmpl.format(ds)
                if url in existing:
                    continue
                try:
                    r = s.head(url, timeout=10, allow_redirects=True)
                    status = r.status_code
                    # Some servers dislike HEAD
                    if status >= 400:
                        r = s.get(url, timeout=10, stream=True, allow_redirects=True)
                        status = r.status_code
                        r.close()
                except Exception:
                    fail += 1
                    if fail > 80:
                        break
                    continue
                if status == 200:
                    fail = 0
                    hits += 1
                    item = {
                        "category": "TVRM",
                        "url": url,
                        "label": f"TVRM {ds}",
                        "source_page": f"gap:{name}_{year}",
                    }
                    found.append(item)
                    existing.add(url)
                else:
                    fail += 1
                    if fail > 80:
                        break
            if hits:
                print(f"{name}_{year}: hits={hits} new_total={len(found)} t={time.time()-t0:.0f}s", flush=True)
                OUT.write_text(json.dumps(found, indent=2), encoding="utf-8")

    if MERGED.exists():
        merged_list = json.loads(MERGED.read_text(encoding="utf-8"))
    else:
        merged_list = []
    uniq = {x["url"]: x for x in merged_list + found}
    merged = list(uniq.values())
    MERGED.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    OUT.write_text(json.dumps(found, indent=2), encoding="utf-8")
    print(f"DONE new_hits={len(found)} merged={len(merged)} t={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
