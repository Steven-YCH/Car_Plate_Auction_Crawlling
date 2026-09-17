# Car License Auction Result Crawler

Build a local database of Hong Kong vehicle registration mark (VRM) auction
results from the Transport Department (TD) website.

Supports both auction types:

- **PVRM** — Personalized Vehicle Registration Marks
- **TVRM** — Traditional Vehicle Registration Marks

## Features

- Discover auction result PDFs from TD index pages
- Optional legacy TVRM URL template probing (many historical filename patterns)
- Download PDFs to `data/raw/` (skips files already on disk)
- Parse plate + auction price (with OCR fallback for older garbled TVRM PDFs)
- Store results in SQLite (`data/db/auction.db`)
- Export consolidated CSV / Excel
- Resumable scrape scripts that skip URLs already stored in the DB

## Project Layout

```text
src/car_auction/
  config.py          # Settings
  dates.py           # Auction-date inference from filenames/headers
  models.py          # AuctionEvent / AuctionLot
  db.py              # SQLite helpers
  discovery/         # Index + date-template discovery
  download.py        # PDF download
  ocr.py             # RapidOCR / PaddleOCR fallback
  parsing/           # PVRM + TVRM parsers
  pipeline.py        # discover → download → parse → load
  cli.py             # CLI
scripts/
  full_scrape.py            # Resumable index scrape (skips stored URLs)
  scrape_templates.py       # Scrape discovered TVRM template URLs
  discover_templates_era.py # Historical TVRM URL probing
  probe_tvrm_gaps.py        # Extra sparse-year TVRM probing
  cleanup_db.py             # Date backfill / duplicate cleanup
data/
  raw/pvrm|tvrm/            # Downloaded PDFs (local only)
  processed/                # CSV/XLSX exports + logs (local only)
  db/auction.db             # SQLite DB (local only)
tests/test_smoke.py         # Small runnable checks
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e .
pip install -r requirements.txt

# Recommended for older/garbled TVRM PDFs:
pip install rapidocr-onnxruntime onnxruntime numpy
# or: pip install -e ".[ocr]"
```

## Usage

```bash
# Index-page discovery only (fast)
python -m car_auction.cli discover --limit 20

# Download + parse a small sample (CLI)
python -m car_auction.cli download --limit 10

# Preferred full/resumable scrape (skips URLs already in DB)
python scripts/full_scrape.py

# Scrape previously discovered TVRM template URLs (also skips stored)
python scripts/scrape_templates.py

# Full historical TVRM probing via CLI (slow; many HEAD requests)
python -m car_auction.cli download --include-templates

# Export CSV + Excel
python -m car_auction.cli export --out data/processed/auction_lots.csv
python -m car_auction.cli export --out data/processed/auction_lots.xlsx
```

Without install, from repo root:

```bash
python -m src.car_auction.cli discover
```

### Incremental behavior

- Existing PDFs in `data/raw/` are **not re-downloaded**
- `scripts/full_scrape.py` and `scripts/scrape_templates.py` **skip URLs already stored** with lots
- Basic CLI `download` still re-parses PDFs it walks; prefer the scripts above for day-to-day runs
- `--include-templates` is opt-in and slow; use only when hunting historical TVRM gaps

## Where to find the results

After scraping/parsing, outputs live under `data/` (gitignored; kept on your machine):

| Path | What it is |
|------|------------|
| `data/db/auction.db` | Canonical SQLite DB (`auction_events` + `auction_lots`) |
| `data/processed/auction_lots.csv` | Flat export of every lot |
| `data/processed/auction_lots.xlsx` | Same export as Excel |
| `data/raw/pvrm/` / `data/raw/tvrm/` | Downloaded source PDFs |

Quick DB check:

```bash
.venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/db/auction.db'); print(c.execute('select category,count(*) from auction_events group by category').fetchall()); print('lots', c.execute('select count(*) from auction_lots').fetchone()[0])"
```

## Parsing notes

| Format | How it is handled |
|--------|-------------------|
| Modern PVRM handouts | Native PDF text; mark-group + amount lines |
| Modern TVRM handouts | Native text triples: `PREFIX / NUMBER / AMOUNT\|U/S\|@AMOUNT` |
| Older TVRM (broken fonts) | RapidOCR + row-wise spatial parse |
| Unsold lots | Stored with `remarks=U/S` and null amount |
| Special fee (`@1,000`) | Stored as amount with `remarks=special_fee` |

Auction dates are inferred from PDF headers / filenames / URLs / TD index labels.

## Be a good citizen

Target site is public TD web content. Keep request rates modest and avoid
high-frequency cron jobs, especially with `--include-templates`.
