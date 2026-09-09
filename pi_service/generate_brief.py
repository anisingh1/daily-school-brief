"""
Calls the Anthropic API directly to categorize the daily school brief
from the current portal + WhatsApp envelope, replacing the daily-school-
brief Claude Code skill's judgment step (see
.claude/skills/daily-school-brief/SKILL.md steps 4-8, which
CATEGORIZATION_RULES below reproduces) for pi_service's unattended,
non-interactive context. PDF attachments are sent as document content
blocks instead of being Read directly, and "today"/"tomorrow" are
computed here (IST) rather than relied on from the model's own sense of
the current date - the API has no equivalent of Claude Code's own
"today's date is..." environment context.

`date` and `warnings` in the returned dict are always overwritten with
code-computed values after the API call, never left to the model - the
model has no reliable way to know the real wall-clock date, and fetch
errors are known facts from the caller, not something to infer from the
message text.
"""

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")
MODEL = "claude-opus-5"


class DailyBrief(BaseModel):
    date: str
    warnings: list[str]
    aviraj_highlight: str | None
    classwork: list[str]
    homework: list[str]
    agenda: list[str]
    dress_code: str | None
    reminders: list[str]


CATEGORIZATION_RULES = """\
You are generating a daily brief for a parent, combining messages from a school
parent portal and a school WhatsApp group. The child this brief is for is
Aviraj.

Today's date (IST, India Standard Time - the school's timezone) is
{today_label} ({today_weekday}). Tomorrow is {tomorrow_label}. Use these
dates for every date-relative rule below - do not use any other notion of
"today" or "tomorrow".

You are given the full set of portal and WhatsApp messages as JSON below,
plus any PDF attachments referenced by those messages (a monthly planner,
an assembly schedule, etc.) as separate document attachments in this same
request - homework/agenda/dress-code details are often inside the document
itself, not the message body text, so read every attached PDF, not just
the message text.

Extract the following, using your own judgment on unstructured free text -
do not pattern-match on fixed keywords:

- Aviraj-specific highlight (`aviraj_highlight`): whenever a message names
  Aviraj specifically (rather than just addressing the class in general),
  call that out - a task or note addressed to him by name is more
  important than a generic class-wide notice. If no message names him
  specifically, leave this null.

- Per-student roster check: some documents (e.g. an assembly schedule)
  pair each day's specific content - a "thought of the day," a "word of
  the day," a specific activity - with the named student assigned to
  present or lead it that day. When that pairing exists, only include the
  content if Aviraj is the student named for the relevant day - check the
  roster/assignment table before including anything from it. If he isn't
  assigned anything for that day, leave that entire item out entirely -
  don't report a classmate's assigned thought/word/activity as if it were
  general class information. A genuinely class-wide detail with no
  per-student assignment attached (e.g. "no school Friday for a holiday")
  is unaffected by this and should still be included normally.

- `classwork`: what was covered in class (typically marked "C.W." in a
  Flow of the Day post) on the most recent school day.

- `homework`: any assignment, reading, or task mentioned for the child to
  do (typically marked "Recap" in a Flow of the Day post).

  Carry-forward rule: `classwork` and `homework` should always reflect the
  most recent school day that had a Flow of the Day post, even if that's
  not today. If today is a weekend or a holiday (so no new Flow of the Day
  post exists for today), carry forward the most recent available post's
  classwork and homework rather than leaving these empty - don't add a
  warning or note explaining why (a holiday/weekend is expected and
  ordinary, not an anomaly worth flagging).

- `agenda`: events, special activities, holidays, timing changes, or
  notices that apply to tomorrow specifically. Content posted at any point
  in the past (e.g. a monthly planner from weeks ago) that happens to
  apply to tomorrow counts just as much as something posted today - you
  are given the full message archive, not just recent messages, so don't
  assume only recent messages matter.

- `dress_code`: any uniform/dress instructions that apply tomorrow (e.g.
  "sports day, wear house colors", "PE kit tomorrow"). Also apply this
  fixed weekly schedule regardless of what the messages say (it isn't
  sourced from the portal/WhatsApp - it's a standing fact about this
  child's week): swimming is every Tuesday and skating is every Thursday.
  If today is Monday, include a reminder to pack swimming dress for
  tomorrow. If today is Wednesday, include a reminder to pack skating
  shoes for tomorrow.

  Override rule: if a message calls out a specific dress code for
  tomorrow (a special event, a change of plan, "no swimming/skating
  tomorrow", etc.), that message-sourced instruction wins - state that one
  instead of the fixed swim/skate reminder above, don't report both. Only
  fall back to the fixed weekly swim/skate reminder when nothing in the
  messages says otherwise for that specific day. If neither applies, leave
  this null.

- `reminders`: anything else worth a parent's attention (fee due dates,
  forms to sign, items to bring, competitions, events) that doesn't fit
  the above, but only if its date falls within the next 5 days from today
  (inclusive of tomorrow). If a message mentions something further out
  than that, don't surface it yet - it'll naturally get picked up on a
  later day's run once it's within the 5-day window.

Leave a field empty (empty list, or null for `aviraj_highlight`/
`dress_code`) rather than forcing content into it when there's nothing
relevant for that field. Set `warnings` to an empty list - it is
overwritten by the caller with accurate fetch-error information after
this call, so leave it as `[]` regardless of what you observe in the
message content. Set `date` to "{tomorrow_label}" - it is also overwritten
by the caller, so its exact value here doesn't matter.

Portal and WhatsApp messages (JSON):
{envelope_json}
"""


def _collect_attachment_blocks(envelope: dict) -> list[dict]:
    blocks = []
    for source in ("portal", "whatsapp"):
        for message in envelope[source]["messages"]:
            for att in message.get("attachments", []):
                saved_as = att.get("saved_as")
                if not saved_as or not Path(saved_as).exists():
                    continue
                data = base64.standard_b64encode(Path(saved_as).read_bytes()).decode("ascii")
                blocks.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                })
    return blocks


def build_prompt(envelope: dict, now: datetime) -> str:
    tomorrow = now + timedelta(days=1)
    envelope_for_prompt = {
        "portal": envelope["portal"]["messages"],
        "whatsapp": envelope["whatsapp"]["messages"],
    }
    return CATEGORIZATION_RULES.format(
        today_label=now.strftime("%A, %B %d, %Y"),
        today_weekday=now.strftime("%A"),
        tomorrow_label=tomorrow.strftime("%A, %B %d, %Y"),
        envelope_json=json.dumps(envelope_for_prompt, indent=2, ensure_ascii=False),
    )


def generate_brief(envelope: dict, now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(IST)
    tomorrow = now + timedelta(days=1)
    date_label = tomorrow.strftime("%A, %B %d, %Y")

    warnings = []
    portal_error = envelope["portal"]["error"]
    whatsapp_error = envelope["whatsapp"]["error"]
    if portal_error:
        warnings.append(f"Couldn't reach school portal: {portal_error}")
    if whatsapp_error:
        warnings.append(f"Couldn't reach WhatsApp group: {whatsapp_error}")

    if not envelope["portal"]["messages"] and not envelope["whatsapp"]["messages"]:
        return {
            "date": date_label,
            "warnings": warnings,
            "aviraj_highlight": None,
            "classwork": [],
            "homework": [],
            "agenda": [],
            "dress_code": None,
            "reminders": [],
        }

    client = anthropic.Anthropic()
    prompt = build_prompt(envelope, now)
    content = _collect_attachment_blocks(envelope) + [{"type": "text", "text": prompt}]
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": content}],
        output_format=DailyBrief,
    )
    data = response.parsed_output.model_dump()
    data["date"] = date_label
    data["warnings"] = warnings
    return data
