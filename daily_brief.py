"""
Gathers filtered messages from the school portal and the WhatsApp log,
and writes a single JSON envelope for the daily-school-brief skill to
read and turn into a categorized brief.

Each source is best-effort: if one fails, its `error` field is set and
`messages` is empty, so the skill can still produce a partial brief
rather than nothing.

Uses a fixed month-start cutoff (see cutoff.py) rather than a persisted
cursor: the portal and WhatsApp log both already retain their own full
history, so re-fetching and re-filtering the whole month every run is
cheap and guarantees a start-of-month monthly planner PDF - or anything
else posted earlier in the month - is never missed, no matter how many
days later it becomes relevant. Portal attachments are downloaded (with
already-downloaded files skipped) so the skill can read PDF content
directly.

USAGE:
    python daily_brief.py
"""

import json
from pathlib import Path
from typing import Any, TypedDict

from cutoff import compute_cutoff
from fetch_whatsapp import fetch_recent_whatsapp_messages
from scrape_udt import fetch_recent_messages

OUTPUT_PATH = Path(__file__).parent / "output" / "daily_brief_input.json"


class SourceResult(TypedDict):
    messages: list[Any]
    error: str | None


def gather() -> dict[str, SourceResult]:
    cutoff = compute_cutoff()
    result: dict[str, SourceResult] = {
        "portal": {"messages": [], "error": None},
        "whatsapp": {"messages": [], "error": None},
    }

    try:
        result["portal"]["messages"] = fetch_recent_messages(cutoff=cutoff, download_attachments=True)
    except Exception as e:  # noqa: BLE001 - best-effort per source, see module docstring
        result["portal"]["error"] = f"{type(e).__name__}: {e}"

    try:
        result["whatsapp"]["messages"] = fetch_recent_whatsapp_messages(cutoff=cutoff)
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
