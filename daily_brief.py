"""
Gathers filtered messages from the school portal and the WhatsApp log,
and writes a single JSON envelope for the daily-school-brief skill to
read and turn into a categorized brief.

Each source is best-effort: if one fails, its `error` field is set and
`messages` is empty, so the skill can still produce a partial brief
rather than nothing.

WhatsApp always uses cutoff.month_anchor() (its Drive log already
retains its own full history, so re-scanning the current month is
enough, and it stays intentionally decoupled from the portal's cursor).
The portal uses portal_archive.py's cursor-or-month-anchor cutoff, merges
newly-fetched messages into the git-committed archive
(data/portal_messages.json), and always returns the FULL merged archive
here - not just the newest fetch - so nothing scraped in the past is
ever missed. The cursor (data/last_run.json) and archive are only
updated when the portal fetch itself succeeds. Portal attachments are
downloaded into data/pdfs/ (skipping already-downloaded files).

Note: data/ must be committed and pushed after this runs for the
archive/cursor to persist across a scheduled cloud routine's fresh
clones - see the daily-school-brief skill, which does this.

USAGE:
    python daily_brief.py
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from cutoff import month_anchor
from fetch_whatsapp import fetch_recent_whatsapp_messages
from portal_archive import compute_portal_cutoff, merge_into_archive, prune_archive, save_archive, save_last_run
from scrape_udt import fetch_recent_messages

OUTPUT_PATH = Path(__file__).parent / "output" / "daily_brief_input.json"


class SourceResult(TypedDict):
    messages: list[Any]
    error: str | None


def gather() -> dict[str, SourceResult]:
    run_started_at = datetime.now()  # noqa: DTZ005 - naive on purpose: fetch_recent_messages compares it against naive portal timestamps; fetch_recent_whatsapp_messages attaches tz itself when needed
    result: dict[str, SourceResult] = {
        "portal": {"messages": [], "error": None},
        "whatsapp": {"messages": [], "error": None},
    }

    try:
        portal_cutoff = compute_portal_cutoff()
        new_messages = fetch_recent_messages(cutoff=portal_cutoff, download_attachments=True)
        full_archive = merge_into_archive(new_messages)
        pruned_archive = prune_archive(full_archive)
        save_archive(pruned_archive)
        save_last_run(run_started_at)
        result["portal"]["messages"] = pruned_archive
    except Exception as e:  # noqa: BLE001 - best-effort per source, see module docstring
        result["portal"]["error"] = f"{type(e).__name__}: {e}"

    try:
        result["whatsapp"]["messages"] = fetch_recent_whatsapp_messages(cutoff=month_anchor())
    except Exception as e:  # noqa: BLE001 - best-effort per source, see module docstring
        result["whatsapp"]["error"] = f"{type(e).__name__}: {e}"

    return result


def run():
    data = gather()
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT_PATH}")
    return data


if __name__ == "__main__":
    run()
