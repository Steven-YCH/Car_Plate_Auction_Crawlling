# Hong Kong Car License Auction Result Crawler

[![CI](https://github.com/Steven-YCH/Car_Plate_Auction_Crawlling/actions/workflows/ci.yml/badge.svg)](https://github.com/Steven-YCH/Car_Plate_Auction_Crawlling/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Build a **local SQLite database** of Hong Kong vehicle registration mark (VRM)
auction results published by the Transport Department (TD).

Supports both auction types:

- **PVRM** — Personalized Vehicle Registration Marks
- **TVRM** — Traditional Vehicle Registration Marks

> Repo folder name keeps the historical spelling `Crawlling`. The Python package
> is `car_auction` / console script `car-auction`.

## Why this project is interesting

Most “portfolio scrapers” hit a clean JSON API. This one has to deal with
**messy real-world government PDFs**:

- TD publishes results as PDFs linked from index pages
- historical TVRM files used many filename patterns over decades
- older PDFs have broken fonts / ToUnicode maps, so OCR fallback is required
- lot rows encode sold prices, unsold (`U/S`), and special-fee `@amount` cases
- auction dates must be inferred from headers, filenames, labels, and URLs

```text
TD index pages / date-URL templates
        │
        ▼
discovery/*  ──►  download (data/raw/)  ──►  parse (+ OCR)  ──►  SQLite
                                                              │
                                                              └─► CSV / Excel
```

## Features

- Discover auction-result PDFs from TD index pages
- Optional legacy TVRM URL template probing
- Polite HTTP client (shared session, User-Agent, delay, retries)
- Skip PDFs already on disk; resumable scrape scripts skip URLs already in DB
- Parse plate + auction price (OCR fallback for older garbled TVRM PDFs)
- Store results in SQLite and export CSV / Excel

## Project layout

```text
src/car_auction/
  config.py          # Settings (paths, delays, UA)
  http.py            # Shared Session + throttle + retry
  dates.py           # Auction-date inference
  models.py          # AuctionEvent / AuctionLot
  db.py              # SQLite helpers
  discovery/         # Index + date-template discovery
  download.py        # PDF download
  ocr.py             # RapidOCR / PaddleOCR fallback
  parsing/           # PVRM + TVRM parsers
  pipeline.py        # discover → download → parse → load
  cli.py             # CLI
scripts/             # Resumable / historical ops workflows
data/                # Local only (gitignored outputs)
tests/               # Pytest smoke checks
```

## Installation

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -e ".[dev]"

# Recommended for older/garbled TVRM PDFs:
pip install -e ".[ocr]"
```

## Usage

```bash
# Index-page discovery only (fast)
car-auction discover --limit 20
# or: python -m car_auction.cli discover --limit 20

# Download + parse a small sample
car-auction download --limit 10

# Preferred full/resumable scrape (skips URLs already in DB)
python scripts/full_scrape.py

# Scrape previously discovered TVRM template URLs
python scripts/scrape_templates.py

# Full historical TVRM probing (slow; many requests)
car-auction download --include-templates

# Export
car-auction export --out data/processed/auction_lots.csv
car-auction export --out data/processed/auction_lots.xlsx
```

### Incremental behavior

- Existing PDFs in `data/raw/` are **not re-downloaded**
- `scripts/full_scrape.py` and `scripts/scrape_templates.py` **skip URLs already stored** with lots
- `--include-templates` is opt-in and slow; use only when hunting historical TVRM gaps

## Outputs

| Path | What it is |
|------|------------|
| `data/db/auction.db` | Canonical SQLite DB (`auction_events` + `auction_lots`) |
| `data/processed/auction_lots.csv` | Flat export of every lot |
| `data/processed/auction_lots.xlsx` | Same export as Excel |
| `data/raw/pvrm/` / `data/raw/tvrm/` | Downloaded source PDFs |

Quick DB check:

```bash
python -c "import sqlite3; c=sqlite3.connect('data/db/auction.db'); print(c.execute('select category,count(*) from auction_events group by category').fetchall()); print('lots', c.execute('select count(*) from auction_lots').fetchone()[0])"
```

## Parsing notes

| Format | How it is handled |
|--------|-------------------|
| Modern PVRM handouts | Native PDF text; mark-group + amount lines |
| Modern TVRM handouts | Native text triples: `PREFIX / NUMBER / AMOUNT\|U/S\|@AMOUNT` |
| Older TVRM (broken fonts) | RapidOCR + row-wise spatial parse |
| Unsold lots | Stored with `remarks=U/S` and null amount |
| Special fee (`@1,000`) | Stored as amount with `remarks=special_fee` |

## Tests

```bash
pytest -q
```

Core unit checks cover date inference, amount tokens, and TVRM token triples.
Optional local PDF integration checks run only when sample PDFs exist under `data/raw/`.

## Be a good citizen

Target site is public TD web content. This project uses a descriptive User-Agent,
request delays, and retries. Keep request rates modest and avoid high-frequency
cron jobs, especially with `--include-templates`.

## License

MIT — see [LICENSE](LICENSE).
