"""
Computes the cutoff used by the orchestrated daily-brief pipeline
(daily_brief.py) for both the portal and WhatsApp fetchers: always 2 days
before the start of the current calendar month.

The portal's activity page and the WhatsApp Drive log both already
retain their own full history (nothing is deleted), so there's no need
to persist a "last run" cursor between runs - re-fetching and
re-filtering the whole month is cheap. The only genuinely expensive
thing to avoid repeating is downloading the same PDF attachment twice;
that's handled separately in scrape_udt.py by skipping a download if the
target file already exists on disk.

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


def compute_cutoff() -> datetime:
    return month_anchor()
