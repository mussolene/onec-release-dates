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


def test_select_year_ago_release_falls_back_to_latest_without_old_enough_row():
    rows = [
        {"version": "1.0.2", "date": "2026-06-10"},
        {"version": "1.0.1", "date": "2026-06-01"},
    ]

    cutoff, baseline = select_year_ago_release(rows, rows[0], 365)

    assert cutoff == dt.date(2025, 6, 10)
    assert baseline == rows[0]
    assert period_rows(rows, cutoff, baseline) == rows


def test_select_year_ago_release_returns_latest_when_latest_is_stale(monkeypatch):
    monkeypatch.setattr(collector, "TODAY", dt.date(2026, 7, 2))
    rows = [
        {"version": "2.0.44.40", "date": "2024-06-04"},
        {"version": "2.0.44.28", "date": "2023-04-03"},
    ]

    cutoff, baseline = select_year_ago_release(rows, rows[0], 365)

    assert cutoff == dt.date(2024, 6, 4)
    assert baseline == rows[0]
    assert period_rows(rows, cutoff, baseline) == [rows[0]]


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

    monkeypatch.setattr(collector, "fetch", lambda url, **kwargs: (200, html))

    rows = collector.parse_its_news_month("202506")

    assert rows == [
        {
            "config_id": "AccountingCorp30_3_0",
            "config_name": "Бухгалтерия предприятия КОРП (3.0)",
            "source_config_id": "AccountingCorp30",
            "version_branch": "3.0",
            "version": "3.0.177.30",
            "date": "2025-06-25",
            "date_ru": "25.06.2025",
            "source": "its.1c.ru news",
            "month": "202506",
            "source_kind": "its",
        }
    ]


def test_erp_uh32_31_release_is_canonicalized_to_erp_uh31():
    row = collector.release_row(
        config_id="ERP_UH32",
        config_name="1С:ERP.Управление холдингом",
        version="3.1.13.24",
        date=dt.date(2025, 4, 6),
        source="its.1c.ru news",
        url="https://its.1c.ru/news/494210",
    )

    assert row["source_config_id"] == "ERP_UH31"
    assert row["config_id"] == "ERP_UH31_3_1"
    assert row["version_branch"] == "3.1"
