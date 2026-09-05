"""
Computes the shared month-start cutoff used for the orchestrated
daily-brief pipeline's WhatsApp fetch, and as the portal's fallback
cutoff when no cursor has been recorded yet (see portal_archive.py):
always 2 days before the start of the current calendar month.

Using "start of month minus 2 days" (rather than exactly day 1) gives
slack for a message posted right at the month boundary and guards
against clock/timezone edge cases.
"""

from datetime import datetime, timedelta


def month_anchor(today: datetime | None = None) -> datetime:
    """2 days before the start of the current calendar month."""
    if today is None:
        today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start - timedelta(days=2)
