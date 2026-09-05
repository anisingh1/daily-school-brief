"""
Gathers filtered messages from the school portal and the WhatsApp log,
and writes a single JSON envelope for the daily-school-brief skill to
read and turn into a categorized brief.

Each source is best-effort: if one fails, its `error` field is set and
`messages` is empty, so the skill can still produce a partial brief
rather than nothing.

Uses a Google-Drive-persisted cursor (see drive_state.py) so each run
only looks back as far as the last successful run, falling back to a
month-anchor floor (2 days before the start of the current month) when
no cursor is available yet - this guarantees a start-of-month monthly
planner PDF is never missed on a fresh setup or after a gap. The cursor
is only advanced when BOTH sources succeed, so a failure causes the next
run to retry the same window rather than silently losing data.

USAGE:
    python daily_brief.py
"""

import json
from datetime import datetime
from pathlib import Path

from scrape_udt import fetch_recent_messages
from fetch_whatsapp import fetch_recent_whatsapp_messages
from drive_state import compute_cutoff, save_last_run

OUTPUT_PATH = Path(__file__).parent / "output" / "daily_brief_input.json"


def gather() -> dict:
    run_started_at = datetime.now()
    cutoff = compute_cutoff()
    result = {
        "portal": {"messages": [], "error": None},
        "whatsapp": {"messages": [], "error": None},
    }

    try:
        result["portal"]["messages"] = fetch_recent_messages(cutoff=cutoff, download_attachments=False)
    except Exception as e:
        result["portal"]["error"] = f"{type(e).__name__}: {e}"

    try:
        result["whatsapp"]["messages"] = fetch_recent_whatsapp_messages(cutoff=cutoff)
    except Exception as e:
        result["whatsapp"]["error"] = f"{type(e).__name__}: {e}"

    if result["portal"]["error"] is None and result["whatsapp"]["error"] is None:
        save_last_run(run_started_at)

    return result


def run():
    data = gather()
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT_PATH}")
    return data


if __name__ == "__main__":
    run()
