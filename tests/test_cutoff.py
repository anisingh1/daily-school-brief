from datetime import datetime

import cutoff


def test_month_anchor_is_two_days_before_month_start():
    today = datetime(2026, 9, 15, 12, 30)
    result = cutoff.month_anchor(today)
    assert result == datetime(2026, 8, 30, 0, 0, 0)


def test_month_anchor_handles_january_rollover():
    today = datetime(2026, 1, 10)
    result = cutoff.month_anchor(today)
    assert result == datetime(2025, 12, 30, 0, 0, 0)


def test_month_anchor_months_back_extends_further_into_the_past():
    today = datetime(2026, 9, 15, 12, 30)
    result = cutoff.month_anchor(today, months_back=3)
    assert result == datetime(2026, 6, 29, 0, 0, 0)


def test_month_anchor_months_back_handles_year_rollover():
    today = datetime(2026, 1, 10)
    result = cutoff.month_anchor(today, months_back=3)
    assert result == datetime(2025, 10, 30, 0, 0, 0)
