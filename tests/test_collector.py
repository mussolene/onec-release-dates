import datetime as dt

from onec_release_dates import collector
from onec_release_dates.collector import period_rows, select_year_ago_release


def test_select_year_ago_release_returns_release_at_or_before_cutoff():
    rows = [
        {"version": "1.0.3", "date": "2026-06-10"},
        {"version": "1.0.2", "date": "2025-06-09"},
        {"version": "1.0.1", "date": "2025-06-01"},
    ]

    cutoff, baseline = select_year_ago_release(rows, rows[0], 365)

    assert cutoff == dt.date(2025, 6, 10)
    assert baseline == rows[1]


def test_select_year_ago_release_returns_none_without_old_enough_row():
    rows = [
        {"version": "1.0.2", "date": "2026-06-10"},
        {"version": "1.0.1", "date": "2026-06-01"},
    ]

    cutoff, baseline = select_year_ago_release(rows, rows[0], 365)

    assert cutoff == dt.date(2025, 6, 10)
    assert baseline is None
    assert period_rows(rows, cutoff, baseline) == rows


def test_parse_its_news_month_reads_panel_date_and_version_links(monkeypatch):
    html = """
    <div class="panel">
      <a data-news-id="495339" href="https://releases.1c.ru/version_files?nick=AccountingCorp30&amp;ver=3.0.177.30">
        <div class="journal-date__day">25</div>
        <div class="journal-date__month">июн</div>
        <div class="journal-date__year">'25</div>
        <div class="link-item news-item">Вышла новая версия 3.0.177.30 "Бухгалтерия предприятия КОРП"</div>
      </a>
    </div>
    """

    monkeypatch.setattr(collector, "fetch", lambda url: (200, html))

    rows = collector.parse_its_news_month("202506")

    assert rows == [
        {
            "config_id": "AccountingCorp30",
            "config_name": "Бухгалтерия предприятия КОРП",
            "version": "3.0.177.30",
            "date": "2025-06-25",
            "date_ru": "25.06.2025",
            "source": "its.1c.ru news",
            "url": "https://its.1c.ru/news/495339",
            "news_id": "495339",
            "news_title": 'Вышла новая версия 3.0.177.30 "Бухгалтерия предприятия КОРП"',
            "month": "202506",
            "source_kind": "its",
        }
    ]
