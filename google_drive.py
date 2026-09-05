"""
Shared Google Drive API helpers: building an authenticated client from a
service account (file path or raw JSON key content), and downloading
small text files by ID.

Used by fetch_whatsapp.py to read the WhatsApp JSONL log.
"""

import io
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def build_client(service_account_json: str):
    if os.path.isfile(service_account_json):
        credentials = service_account.Credentials.from_service_account_file(
            service_account_json, scopes=SCOPES
        )
    else:
        info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    return build("drive", "v3", credentials=credentials)


def download_text(drive_service, file_id: str) -> str:
    request = drive_service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8")
