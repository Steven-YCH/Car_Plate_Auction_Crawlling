"""Era-chunked TVRM discovery to survive long gaps between auctions."""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/tvrm_template_urls_era.json"
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

    # Chunked eras so a quiet year doesn't stop the whole strategy.
    jobs = []
    # Modern chi: every year chunk 2022..today
    y = date.today().year
    for year in range(y, 2021, -1):
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        if year == y:
            end = date.today()
        jobs.append(
            (
                f"chi_{year}",
                "https://www.td.gov.hk/filemanager/tc/content_4804/tvrm_auction_result_{}_chi.pdf",
                "%Y%m%d",
                start,
                end,
                (),  # all days inside year
                370,
            )
        )
        jobs.append(
            (
                f"plain_{year}",
                "https://www.td.gov.hk/filemanager/tc/content_4804/tvrm_auction_result_{}.pdf",
                "%Y%m%d",
                start,
                end,
                (),
                370,
            )
        )

    # Legacy handouts by year
    for year in range(2015, 2007, -1):
        jobs.append(
            (
                f"handout_{year}",
                "https://www.td.gov.hk/filemanager/common/auction%20result%20handout%20{}.pdf",
                "%d-%m-%Y",
                date(year, 1, 1),
                date(year, 12, 31),
                (),
                370,
            )
        )
        jobs.append(
            (
                f"results_handout_{year}",
                "https://www.td.gov.hk/filemanager/common/auction%20results%20handout_{}.pdf",
                "%Y%m%d",
                date(year, 1, 1),
                date(year, 12, 31),
                (5, 6),
                120,
            )
        )
        jobs.append(
            (
                f"tvrm_results_handout_{year}",
                "https://www.td.gov.hk/filemanager/common/tvrm%20auction%20results%20handout_{}.pdf",
                "%Y%m%d",
                date(year, 1, 1),
                date(year, 12, 31),
                (5, 6),
                120,
            )
        )
        jobs.append(
            (
                f"unpadded_{year}",
                "https://www.td.gov.hk/filemanager/common/tvrm%20auction%20result%20{}.pdf",
                "unpadded",
                date(year, 1, 1),
                date(year, 12, 31),
                (),
                370,
            )
        )

    for year in range(2022, 2014, -1):
        jobs.append(
            (
                f"auction-result-handout_{year}",
                "https://www.td.gov.hk/filemanager/common/auction-result-handout_{}.pdf",
                "%Y%m%d",
                date(year, 1, 1),
                date(year, 12, 31),
                (5, 6),
                120,
            )
        )
        jobs.append(
            (
                f"tvrm_auction_result_ddmm_{year}",
                "https://www.td.gov.hk/filemanager/common/tvrm_auction_result_{}.pdf",
                "%d_%m_%Y",
                date(year, 1, 1),
                date(year, 12, 31),
                (5, 6),
                120,
            )
        )

    for year in range(2019, 2014, -1):
        jobs.append(
            (
                f"aucr05_{year}",
                "https://www.td.gov.hk/filemanager/common/aucr05_{}183029.pdf",
                "%Y%m%d",
                date(year, 1, 1),
                date(year, 12, 31),
                (5, 6),
                120,
            )
        )

    for name, tmpl, fmt, start, end, weekdays, max_fail in jobs:
        fail = 0
        hits = 0
        for d in daterange(start, end, weekdays):
            if fmt == "unpadded":
                ds = f"{d.day}-{d.month}-{d.year}"
            else:
                ds = d.strftime(fmt)
            url = tmpl.format(ds)
            try:
                r = s.get(url, timeout=10, stream=True, allow_redirects=True)
                status = r.status_code
                r.close()
            except Exception:
                fail += 1
                if fail > max_fail:
                    break
                continue
            if status == 200:
                fail = 0
                hits += 1
                found.append(
                    {
                        "category": "TVRM",
                        "url": url,
                        "label": f"TVRM {ds}",
                        "source_page": f"template:{name}",
                    }
                )
            else:
                fail += 1
                if fail > max_fail:
                    break
        if hits:
            print(f"{name}: hits={hits} total={len(found)} t={time.time()-t0:.0f}s", flush=True)
            OUT.write_text(json.dumps(found, indent=2), encoding="utf-8")

    v1 = json.loads(MERGED.read_text(encoding="utf-8")) if MERGED.exists() else []
    uniq = {x["url"]: x for x in v1 + found}
    merged = list(uniq.values())
    MERGED.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    OUT.write_text(json.dumps(found, indent=2), encoding="utf-8")
    print(f"DONE era_hits={len(found)} merged={len(merged)}", flush=True)


if __name__ == "__main__":
    main()
