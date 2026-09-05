"""
Persists the portal message archive and a "last run" cursor in this git
repo itself (under data/), instead of an external store like Google
Drive - so this data survives across scheduled-cloud-routine runs, as
long as whoever invokes daily_brief.py commits and pushes data/
afterward (see the daily-school-brief skill, which does this as an
explicit step).

Unlike the WhatsApp side (whose Drive log already retains full history
on its own), the portal's activity page shows an unknown retention
window, so daily_brief.py builds its own permanent archive here: every
message ever scraped, deduplicated by message id, merged with each new
fetch. The brief is always generated from the FULL archive, never just
the newest fetch, so nothing posted at any point in the past is ever
missed once cursor efficiency is reintroduced.

Cutoff logic: if no cursor has been saved yet (fresh setup, or the
data/ directory was reset), fall back to cutoff.month_anchor() so a
start-of-month document is still caught on the first run. Otherwise,
use the last run's timestamp - only fetch what's new, merge it into the
archive, and advance the cursor.
"""

import json
from datetime import datetime
from pathlib import Path

from dateutil import parser as dateparser

from cutoff import month_anchor

DATA_DIR = Path(__file__).parent / "data"
ARCHIVE_PATH = DATA_DIR / "portal_messages.json"
LAST_RUN_PATH = DATA_DIR / "last_run.json"


def read_last_run() -> datetime | None:
    if not LAST_RUN_PATH.exists():
        return None
    data = json.loads(LAST_RUN_PATH.read_text())
    raw = data.get("last_run")
    if not raw:
        return None
    return dateparser.parse(raw)


def save_last_run(dt: datetime) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    LAST_RUN_PATH.write_text(json.dumps({"last_run": dt.isoformat()}, indent=2))


def compute_portal_cutoff() -> datetime:
    last_run = read_last_run()
    if last_run is not None:
        return last_run
    return month_anchor()


def load_archive() -> list[dict]:
    if not ARCHIVE_PATH.exists():
        return []
    return json.loads(ARCHIVE_PATH.read_text())


def merge_into_archive(new_messages: list[dict]) -> list[dict]:
    existing = load_archive()
    by_id = {m["id"]: m for m in existing}
    for m in new_messages:
        by_id[m["id"]] = m
    merged = list(by_id.values())
    merged.sort(key=lambda m: m["posted_at"], reverse=True)
    return merged


def save_archive(messages: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    ARCHIVE_PATH.write_text(json.dumps(messages, indent=2, ensure_ascii=False))
