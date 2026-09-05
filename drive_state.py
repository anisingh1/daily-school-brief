"""
Persists a "last run" cursor for the orchestrated daily-brief pipeline
(daily_brief.py) on Google Drive, so runs only need to look back as far
as the last successful run instead of re-fetching a fixed window every
time.

Falls back to a month-anchor floor (2 days before the start of the
current calendar month) when no cursor has been saved yet, so a
start-of-month monthly planner PDF is never missed on a fresh setup or
after a gap.

Uses the same Google Drive service account as fetch_whatsapp.py (see
google_drive.py), but the state file needs to be shared with it as
Editor (not just Viewer), since this module writes to it.

SETUP:
    - Create an empty Drive file (e.g. containing `{}`) for the cursor.
    - Share it with the service account's email as Editor.
    - Set STATE_DRIVE_FILE_ID to that file's Drive file ID in .env.
"""

import json
import os
from datetime import datetime, timedelta

from dateutil import parser as dateparser
from dotenv import load_dotenv

import google_drive

load_dotenv()

SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
STATE_DRIVE_FILE_ID = os.getenv("STATE_DRIVE_FILE_ID")


def month_anchor(today: datetime | None = None) -> datetime:
    """2 days before the start of the current calendar month."""
    if today is None:
        today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start - timedelta(days=2)


def read_last_run() -> datetime | None:
    if not SERVICE_ACCOUNT_JSON or not STATE_DRIVE_FILE_ID:
        return None
    drive_service = google_drive.build_client(SERVICE_ACCOUNT_JSON)
    text = google_drive.download_text(drive_service, STATE_DRIVE_FILE_ID)
    data = json.loads(text) if text.strip() else {}
    raw = data.get("last_run")
    if not raw:
        return None
    return dateparser.parse(raw)


def save_last_run(dt: datetime) -> None:
    if not SERVICE_ACCOUNT_JSON or not STATE_DRIVE_FILE_ID:
        return
    try:
        drive_service = google_drive.build_client(SERVICE_ACCOUNT_JSON)
        google_drive.upload_text(
            drive_service, STATE_DRIVE_FILE_ID, json.dumps({"last_run": dt.isoformat()})
        )
    except Exception as e:
        print(f"Warning: failed to save last_run cursor: {e}")


def compute_cutoff() -> datetime:
    try:
        last_run = read_last_run()
    except Exception as e:
        print(f"Warning: failed to read last_run cursor, falling back to month anchor: {e}")
        last_run = None
    if last_run is not None:
        return last_run
    return month_anchor()
