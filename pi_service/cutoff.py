"""
Computes the shared month-start cutoff used for the orchestrated
daily-brief pipeline's WhatsApp fetch, and as the portal's fallback
cutoff when no cursor has been recorded yet (see portal_archive.py):
by default, 2 days before the start of the current calendar month.

Using "start of month minus 2 days" (rather than exactly day 1) gives
slack for a message posted right at the month boundary and guards
against clock/timezone edge cases.

`months_back` shifts the anchor earlier by whole calendar months first
(so `months_back=3` reaches back to 2 months before the current one,
then applies the same 2-day slack) - used to widen the lookback beyond
just the current month.
"""

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta


def month_anchor(today: datetime | None = None, months_back: int = 1) -> datetime:
    """2 days before the start of the calendar month `months_back` months ago."""
    if today is None:
        today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    anchor_month_start = month_start - relativedelta(months=months_back - 1)
    return anchor_month_start - timedelta(days=2)
