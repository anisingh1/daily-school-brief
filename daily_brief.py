"""
Gathers filtered messages from the school portal and the WhatsApp log,
and writes a single JSON envelope for the daily-school-brief skill to
read and turn into a categorized brief.

Each source is best-effort: if one fails, its `error` field is set and
`messages` is empty, so the skill can still produce a partial brief
rather than nothing.

USAGE:
    python daily_brief.py
"""

import json
from pathlib import Path

from scrape_udt import fetch_recent_messages
from fetch_whatsapp import fetch_recent_whatsapp_messages

OUTPUT_PATH = Path(__file__).parent / "output" / "daily_brief_input.json"


def gather() -> dict:
    result = {
        "portal": {"messages": [], "error": None},
        "whatsapp": {"messages": [], "error": None},
    }

    try:
        result["portal"]["messages"] = fetch_recent_messages(download_attachments=False)
    except Exception as e:
        result["portal"]["error"] = f"{type(e).__name__}: {e}"

    try:
        result["whatsapp"]["messages"] = fetch_recent_whatsapp_messages()
    except Exception as e:
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
