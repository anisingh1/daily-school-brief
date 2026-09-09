"""
Always-on entrypoint for the daily school brief pi_service: polls the
school portal (60 min) and WhatsApp (10 min) for new content, forces one
daily regeneration as a backstop (~7:30pm IST) so date-relative fields
stay correct even without new messages, and serves the latest brief on a
LAN-only web page. Run via `python -m pi_service.service`.
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask

from pi_service import fetch_whatsapp, generate_brief, portal_archive, render_brief, scrape_udt
from pi_service.cutoff import month_anchor

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")
WHATSAPP_POLL_SECONDS = 600
PORTAL_POLL_SECONDS = 3600
PORT = int(os.getenv("PORT", "8765"))

OUTPUT_DIR = Path(__file__).parent / "output"
CONTENT_PATH = OUTPUT_DIR / "daily_brief_content.json"
LAST_ATTEMPT_PATH = OUTPUT_DIR / "last_attempt.json"

app = Flask(__name__)


class PortalPoller:
    """Fetches new portal messages since the cursor and merges them into
    the archive. `tick()` returns True if anything new was fetched (the
    brief itself is always built from the FULL archive - see
    regenerate_brief - not from this method's return value)."""

    def __init__(self) -> None:
        self.last_error: str | None = None

    def tick(self) -> bool:
        try:
            cutoff = portal_archive.compute_portal_cutoff()
            new_messages = scrape_udt.fetch_recent_messages(cutoff=cutoff, download_attachments=True)
            merged = portal_archive.merge_into_archive(new_messages)
            pruned = portal_archive.prune_archive(merged)
            portal_archive.save_archive(pruned)
            portal_archive.save_last_run(datetime.now())
            self.last_error = None
            return bool(new_messages)
        except Exception as e:  # noqa: BLE001 - best-effort per source, matches daily_brief.py's contract
            self.last_error = f"{type(e).__name__}: {e}"
            return False


class WhatsAppPoller:
    """Re-fetches the full WhatsApp window every tick (cheap IMAP call)
    and detects new content by diffing against the previous tick's
    result, rather than a persisted cursor - see the design doc for why a
    cursor would silently drop older-but-still-relevant messages from the
    brief."""

    def __init__(self) -> None:
        self.last_messages: list[dict] | None = None
        self.last_error: str | None = None
        self._previous_messages: list[dict] | None = None

    def tick(self) -> bool:
        try:
            messages = fetch_whatsapp.fetch_recent_whatsapp_messages(cutoff=month_anchor(months_back=3))
        except Exception as e:  # noqa: BLE001 - best-effort per source, matches daily_brief.py's contract
            self.last_error = f"{type(e).__name__}: {e}"
            return False
        self.last_error = None
        self.last_messages = messages
        previous = self._previous_messages
        self._previous_messages = messages
        if previous is None:
            return False
        return messages != previous
