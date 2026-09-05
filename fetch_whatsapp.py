"""
Fetches WhatsApp group messages forwarded via phone automation.

Messages are captured by a MacroDroid rule on an Android phone (see
docs/PHONE_SETUP.md) which appends one JSON line per message to a file
in a Google Drive folder. This module reads that file via the Drive API
using a service account (see google_drive.py) and filters to a rolling
lookback window, or an explicit absolute cutoff when one is provided
(used by daily_brief.py's cross-run cursor - see drive_state.py).

SETUP:
    - Create a Google Cloud service account with Drive API access.
    - Share the Drive folder containing the WhatsApp log file with the
      service account's email as Viewer.
    - Set GOOGLE_SERVICE_ACCOUNT_JSON (a file path, or the raw JSON key
      content) and WHATSAPP_DRIVE_FILE_ID (the Drive file ID of the
      JSONL log) in .env.

USAGE:
    python fetch_whatsapp.py
"""

import json
import os
from datetime import datetime, timedelta

from dateutil import parser as dateparser
from dotenv import load_dotenv

import google_drive

load_dotenv()

SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
DRIVE_FILE_ID = os.getenv("WHATSAPP_DRIVE_FILE_ID")
LOOKBACK_HOURS = float(os.getenv("LOOKBACK_HOURS", "36"))


def parse_jsonl(text: str) -> list[dict]:
    messages = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def filter_recent(
    messages: list[dict], lookback_hours: float | None = None, cutoff: datetime | None = None
) -> list[dict]:
    if cutoff is None:
        if lookback_hours is None:
            lookback_hours = LOOKBACK_HOURS
        cutoff = datetime.now().astimezone() - timedelta(hours=lookback_hours)
    filtered = []
    for m in messages:
        raw_ts = m.get("timestamp")
        if not raw_ts:
            continue
        try:
            ts = dateparser.parse(raw_ts)
        except (ValueError, TypeError, OverflowError):
            continue
        if ts.tzinfo is None:
            ts = ts.astimezone()
        if ts >= cutoff:
            filtered.append(m)
    filtered.sort(key=lambda m: dateparser.parse(m["timestamp"]).astimezone())
    return filtered


def fetch_recent_whatsapp_messages(
    lookback_hours: float | None = None, cutoff: datetime | None = None
) -> list[dict]:
    if not SERVICE_ACCOUNT_JSON or not DRIVE_FILE_ID:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON and/or WHATSAPP_DRIVE_FILE_ID are not set."
        )
    drive_service = google_drive.build_client(SERVICE_ACCOUNT_JSON)
    text = google_drive.download_text(drive_service, DRIVE_FILE_ID)
    messages = parse_jsonl(text)
    return filter_recent(messages, lookback_hours=lookback_hours, cutoff=cutoff)


if __name__ == "__main__":
    for msg in fetch_recent_whatsapp_messages():
        print(msg)
