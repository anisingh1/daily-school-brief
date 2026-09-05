"""
Fetches WhatsApp group messages forwarded via phone automation.

Messages are captured by a MacroDroid rule on an Android phone (see
docs/PHONE_SETUP.md) which appends one JSON line per message to a file
in a Google Drive folder. This module reads that file via the Drive API
using a service account and filters to a rolling lookback window.

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

import io
import json
import os
from datetime import datetime, timedelta

from dateutil import parser as dateparser
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
DRIVE_FILE_ID = os.getenv("WHATSAPP_DRIVE_FILE_ID")
LOOKBACK_HOURS = float(os.getenv("LOOKBACK_HOURS", "36"))


def _drive_client():
    if os.path.isfile(SERVICE_ACCOUNT_JSON):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
    else:
        info = json.loads(SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    return build("drive", "v3", credentials=credentials)


def download_jsonl_text(drive_service, file_id: str) -> str:
    request = drive_service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8")


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


def filter_recent(messages: list[dict], lookback_hours: float) -> list[dict]:
    cutoff = datetime.now().astimezone() - timedelta(hours=lookback_hours)
    filtered = []
    for m in messages:
        raw_ts = m.get("timestamp")
        if not raw_ts:
            continue
        try:
            ts = dateparser.parse(raw_ts)
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.astimezone()
        if ts >= cutoff:
            filtered.append(m)
    filtered.sort(key=lambda m: m["timestamp"])
    return filtered


def fetch_recent_whatsapp_messages(lookback_hours: float | None = None) -> list[dict]:
    if lookback_hours is None:
        lookback_hours = LOOKBACK_HOURS
    if not SERVICE_ACCOUNT_JSON or not DRIVE_FILE_ID:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON and/or WHATSAPP_DRIVE_FILE_ID are not set."
        )
    drive_service = _drive_client()
    text = download_jsonl_text(drive_service, DRIVE_FILE_ID)
    messages = parse_jsonl(text)
    return filter_recent(messages, lookback_hours)


if __name__ == "__main__":
    for msg in fetch_recent_whatsapp_messages():
        print(msg)
