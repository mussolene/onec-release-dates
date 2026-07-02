import datetime as dt

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
