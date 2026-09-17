"""Date-template based discovery for legacy TVRM PDFs.

TD has used multiple naming patterns over time. Templates below capture common
historical filename formats used on the Transport Department site.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List

import requests

from ..config import discovery
from .pvrm_index import DiscoveredPDF


@dataclass
class TemplateStrategy:
    name: str
    url_template: str  # must contain one '{}' for the date fragment
    date_format: str
    start_date: date
    end_date: date
    max_fail_streak: int = 365
    # weekdays to probe: 0=Mon .. 5=Sat, 6=Sun. Empty = every day.
    weekdays: tuple[int, ...] = (5, 6)  # auctions are usually weekends


def _daterange_desc(start: date, end: date, weekdays: tuple[int, ...] = ()) -> Iterable[date]:
    cur = end
    while cur >= start:
        if not weekdays or cur.weekday() in weekdays:
            yield cur
        cur -= timedelta(days=1)


def _full_url(path_or_template: str, date_str: str) -> str:
    path = path_or_template.format(date_str)
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return discovery.base_url.rstrip("/") + path


def _default_strategies() -> List[TemplateStrategy]:
    today = date.today()
    return [
        # Modern Chinese filename under content_4804
        TemplateStrategy(
            name="content_4804_yyyymmdd_chi",
            url_template="/filemanager/tc/content_4804/tvrm_auction_result_{}_chi.pdf",
            date_format="%Y%m%d",
            start_date=date(2022, 1, 1),
            end_date=today,
            max_fail_streak=120,
        ),
        # Same folder without _chi suffix
        TemplateStrategy(
            name="content_4804_yyyymmdd",
            url_template="/filemanager/tc/content_4804/tvrm_auction_result_{}.pdf",
            date_format="%Y%m%d",
            start_date=date(2018, 1, 1),
            end_date=today,
            max_fail_streak=120,
        ),
        # common/tvrm_auction_result_dd_mm_YYYY.pdf
        TemplateStrategy(
            name="common_tvrm_auction_result_dd_mm_yyyy",
            url_template="/filemanager/common/tvrm_auction_result_{}.pdf",
            date_format="%d_%m_%Y",
            start_date=date(2000, 1, 1),
            end_date=date(2022, 12, 31),
            max_fail_streak=120,
        ),
        # common/{date} tvrm auction result.pdf
        TemplateStrategy(
            name="common_prefix_date_tvrm_auction_result",
            url_template="/filemanager/common/{}%20tvrm%20auction%20result.pdf",
            date_format="%Y%m%d",
            start_date=date(2000, 1, 1),
            end_date=date(2019, 12, 31),
            max_fail_streak=120,
        ),
        # common/tvrm auction result_dd.mm.YYYY.pdf
        TemplateStrategy(
            name="common_tvrm_auction_result_dd.mm.yyyy",
            url_template="/filemanager/common/tvrm%20auction%20result_{}.pdf",
            date_format="%d.%m.%Y",
            start_date=date(2000, 1, 1),
            end_date=date(2022, 12, 31),
            max_fail_streak=120,
        ),
        # common/auction-result-handout_YYYYMMDD.pdf
        TemplateStrategy(
            name="common_auction-result-handout_yyyymmdd",
            url_template="/filemanager/common/auction-result-handout_{}.pdf",
            date_format="%Y%m%d",
            start_date=date(2000, 1, 1),
            end_date=date(2022, 12, 31),
            max_fail_streak=120,
        ),
        # common/tvrm auction results handout_YYYYMMDD.pdf
        TemplateStrategy(
            name="common_tvrm_auction_results_handout_yyyymmdd",
            url_template="/filemanager/common/tvrm%20auction%20results%20handout_{}.pdf",
            date_format="%Y%m%d",
            start_date=date(2008, 1, 1),
            end_date=date(2015, 12, 31),
            max_fail_streak=120,
        ),
        # common/aucr05_YYYYMMDD183029.pdf
        TemplateStrategy(
            name="common_aucr05_yyyymmdd183029",
            url_template="/filemanager/common/aucr05_{}183029.pdf",
            date_format="%Y%m%d",
            start_date=date(2015, 1, 1),
            end_date=date(2019, 12, 31),
            max_fail_streak=120,
        ),
        # common/auction results handout_YYYYMMDD.pdf
        TemplateStrategy(
            name="common_auction_results_handout_yyyymmdd",
            url_template="/filemanager/common/auction%20results%20handout_{}.pdf",
            date_format="%Y%m%d",
            start_date=date(2008, 1, 1),
            end_date=date(2012, 12, 31),
            max_fail_streak=120,
        ),
        # common/auction result handout dd-mm-YYYY.pdf
        TemplateStrategy(
            name="common_auction_result_handout_dd-mm-yyyy",
            url_template="/filemanager/common/auction%20result%20handout%20{}.pdf",
            date_format="%d-%m-%Y",
            start_date=date(2008, 1, 1),
            end_date=date(2015, 12, 31),
            max_fail_streak=400,
            weekdays=(),  # can fall on weekdays
        ),
        # common/tvrm auction result d-m-YYYY.pdf  (unpadded)
        TemplateStrategy(
            name="common_tvrm_auction_result_d-m-yyyy",
            url_template="/filemanager/common/tvrm%20auction%20result%20{}.pdf",
            date_format="%-d-%-m-%Y" if False else "%d-%m-%Y",  # Windows: handled below
            start_date=date(2008, 1, 1),
            end_date=date(2017, 12, 31),
            max_fail_streak=400,
            weekdays=(),
        ),
    ]


def _format_date(d: date, fmt: str) -> str:
    """Format date; support unpadded d-m-Y used by some legacy URLs."""

    if fmt in {"%d-%m-%Y", "unpadded-d-m-Y"}:
        # Produce both padded and rely on strategy name for unpadded variant.
        return d.strftime("%d-%m-%Y")
    if fmt == "%d.%m.%Y":
        return d.strftime("%d.%m.%Y")
    return d.strftime(fmt)


def _format_date_unpadded(d: date) -> str:
    return f"{d.day}-{d.month}-{d.year}"


def discover_tvrm_pdfs_from_templates(
    strategies: Iterable[TemplateStrategy] | None = None,
    *,
    session: requests.Session | None = None,
) -> Iterable[DiscoveredPDF]:
    """Yield DiscoveredPDF entries by probing legacy date-based URLs."""

    if strategies is None:
        strategies = _default_strategies()

    sess = session or requests.Session()

    for strat in strategies:
        fail_streak = 0
        for d in _daterange_desc(strat.start_date, strat.end_date, strat.weekdays):
            if strat.name.endswith("d-m-yyyy"):
                date_str = _format_date_unpadded(d)
            else:
                date_str = _format_date(d, strat.date_format)
            url = _full_url(strat.url_template, date_str)

            try:
                # Prefer GET stream over HEAD: TD sometimes answers HEAD poorly.
                resp = sess.get(url, timeout=15, stream=True, allow_redirects=True)
                status = resp.status_code
                resp.close()
            except requests.RequestException:
                fail_streak += 1
                if fail_streak > strat.max_fail_streak:
                    break
                continue

            if status == 200:
                fail_streak = 0
                yield DiscoveredPDF(
                    category="TVRM",
                    url=url,
                    label=f"TVRM auction result {date_str}",
                    source_page=f"template:{strat.name}",
                )
            else:
                fail_streak += 1
                if fail_streak > strat.max_fail_streak:
                    break
