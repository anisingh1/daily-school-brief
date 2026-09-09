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
from html import escape
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


def next_daily_backstop(now: datetime, hour: int = 19, minute: int = 30) -> datetime:
    """Next occurrence of `hour:minute` at or after `now`, in `now`'s own
    timezone. Returns tomorrow's occurrence if `now` is already at or past
    today's."""
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _write_last_attempt(succeeded: bool, error: str | None) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    LAST_ATTEMPT_PATH.write_text(json.dumps(
        {"succeeded": succeeded, "at": datetime.now(IST).isoformat(), "error": error},
        indent=2,
    ))


def regenerate_brief(portal_poller: PortalPoller, whatsapp_poller: WhatsAppPoller, lock: threading.Lock) -> None:
    """Builds the current envelope from each poller's latest known state,
    calls the LLM, and writes the content JSON - or, on failure, leaves
    the last successfully-generated content untouched and records the
    failure for the web page (which re-renders HTML from this JSON on
    every request) to surface instead."""
    with lock:
        envelope = {
            "portal": {"messages": portal_archive.load_archive(), "error": portal_poller.last_error},
            "whatsapp": {"messages": whatsapp_poller.last_messages or [], "error": whatsapp_poller.last_error},
        }
        try:
            data = generate_brief.generate_brief(envelope)
            OUTPUT_DIR.mkdir(exist_ok=True)
            CONTENT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            _write_last_attempt(succeeded=True, error=None)
        except Exception as e:  # noqa: BLE001 - keep serving the last good brief rather than crashing the service
            _write_last_attempt(succeeded=False, error=f"{type(e).__name__}: {e}")


_NO_BRIEF_PLACEHOLDER = "<h1>Daily School Brief</h1><p>No brief generated yet.</p>"


@app.route("/")
def index() -> str:
    if not CONTENT_PATH.exists():
        return _NO_BRIEF_PLACEHOLDER

    try:
        data = json.loads(CONTENT_PATH.read_text())
    except json.JSONDecodeError:
        # Content file may be mid-write (regenerate_brief's writes are not
        # atomic and this route holds no lock coordinating with it) -
        # degrade to the placeholder rather than a 500.
        return _NO_BRIEF_PLACEHOLDER

    banner_html = ""
    if LAST_ATTEMPT_PATH.exists():
        try:
            attempt = json.loads(LAST_ATTEMPT_PATH.read_text())
            if not attempt["succeeded"]:
                banner_html = (
                    '<div style="max-width: 600px; margin: 0 auto 16px auto; padding: 12px 16px; '
                    'background: #FEE2E2; border-left: 4px solid #DC2626; border-radius: 4px; '
                    'font-size: 14px;">'
                    f'Last regeneration attempt at {escape(attempt["at"])} failed: {escape(attempt["error"])}. '
                    "Showing the last successful brief below."
                    "</div>"
                )
        except (json.JSONDecodeError, KeyError):
            # Sidecar file may be mid-write too; the brief content itself
            # can still be perfectly readable, so just skip the banner.
            pass
    return render_brief.render_brief_html(data, banner_html=banner_html)


def main() -> None:
    lock = threading.Lock()
    portal_poller = PortalPoller()
    whatsapp_poller = WhatsAppPoller()

    def whatsapp_loop() -> None:
        while True:
            if whatsapp_poller.tick():
                regenerate_brief(portal_poller, whatsapp_poller, lock)
            time.sleep(WHATSAPP_POLL_SECONDS)

    def portal_loop() -> None:
        while True:
            if portal_poller.tick():
                regenerate_brief(portal_poller, whatsapp_poller, lock)
            time.sleep(PORTAL_POLL_SECONDS)

    def backstop_loop() -> None:
        while True:
            now = datetime.now(IST)
            next_run = next_daily_backstop(now)
            time.sleep((next_run - now).total_seconds())
            regenerate_brief(portal_poller, whatsapp_poller, lock)

    for target in (whatsapp_loop, portal_loop, backstop_loop):
        threading.Thread(target=target, daemon=True).start()

    app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
