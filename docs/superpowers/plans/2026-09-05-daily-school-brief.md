# Daily School Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every evening at ~7:30pm, automatically produce a push notification covering homework, tomorrow's school agenda, tomorrow's dress code, and other reminders, pulled from the school web portal and a phone-forwarded WhatsApp log.

**Architecture:** Two independent fetcher scripts (portal via existing `scrape_udt.py`, WhatsApp via a new Google Drive API reader) feed a small orchestrator (`daily_brief.py`) that writes a combined JSON file. A Claude skill reads that file, categorizes the content, and sends a push notification. A scheduled cloud routine (tied to the user's claude.ai account, not the Mac) clones this project from a private GitHub repo each evening and runs the pipeline.

**Tech Stack:** Python 3, `requests`/`beautifulsoup4` (existing), `google-api-python-client` + `google-auth` (new, for Drive API), `pytest` (new, for tests). MacroDroid + a folder-sync app on Android (outside this repo). Git + a private GitHub repo (new).

Spec: `docs/superpowers/specs/2026-09-05-daily-school-brief-design.md`

---

### Task 1: Initialize git and push to a private GitHub repo

**Files:**
- No new files — this is repo setup.

- [ ] **Step 1: Initialize the repo**

Run: `git init && git add -A && git status`
Expected: shows `scrape_udt.py`, `README.md`, `requirements.txt`, `.env.example`, `.gitignore`, and the `docs/` tree as staged. Confirm `.env` and `output/` do NOT appear (already covered by `.gitignore`).

- [ ] **Step 2: First commit**

```bash
git commit -m "Initial commit: UDT portal scraper + daily school brief spec"
```

- [ ] **Step 3: Create a private GitHub repo and push**

Requires the `gh` CLI authenticated as the user. Confirm with the user before running (this creates a remote, user-visible resource):

```bash
gh repo create daily-school-brief --private --source=. --remote=origin --push
```

Expected: prints the new repo URL, e.g. `https://github.com/<user>/daily-school-brief`. Keep this URL — it's needed in Task 9.

---

### Task 2: Rolling-window lookback in `scrape_udt.py`

**Files:**
- Modify: `scrape_udt.py`
- Test: `tests/test_scrape_udt.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scrape_udt.py`:

```python
from datetime import datetime, timedelta

import pytest


def _msg(offset_hours, msg_id):
    posted = datetime.now() - timedelta(hours=offset_hours)
    return {
        "id": msg_id,
        "title": "t",
        "posted_at": posted.isoformat(),
        "body": "b",
        "attachments": [],
    }


def test_filter_recent_includes_message_within_window():
    from scrape_udt import filter_recent

    messages = [_msg(1, "recent")]
    result = filter_recent(messages, lookback_hours=36)
    assert len(result) == 1


def test_filter_recent_excludes_message_before_cutoff():
    from scrape_udt import filter_recent

    messages = [_msg(40, "old")]
    result = filter_recent(messages, lookback_hours=36)
    assert result == []


def test_filter_recent_sorts_most_recent_first():
    from scrape_udt import filter_recent

    messages = [_msg(30, "a"), _msg(2, "b"), _msg(10, "c")]
    result = filter_recent(messages, lookback_hours=36)
    assert [m["id"] for m in result] == ["b", "c", "a"]


def test_login_raises_on_failed_login():
    from scrape_udt import login

    class FakeResponse:
        text = '<div id="login-form"></div>'

        def raise_for_status(self):
            pass

    class FakeSession:
        def post(self, *args, **kwargs):
            return FakeResponse()

    with pytest.raises(RuntimeError):
        login(FakeSession())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scrape_udt.py -v`
Expected: FAIL — `ImportError: cannot import name 'filter_recent'` (and `'login'`), since neither exists yet.

- [ ] **Step 3: Refactor `scrape_udt.py`**

Replace the CONFIG section (from the `load_dotenv()` call through the `FILE_PATH_RE` line, currently lines 34–65) with:

```python
load_dotenv()

BASE_URL = os.getenv("UDT_BASE_URL", "https://sarvottam.udtweb.com")
LOGIN_URL = f"{BASE_URL}/Logins/index"
ACTIVITY_URL = f"{BASE_URL}/parents/activity?type=3"

USERNAME = os.getenv("UDT_USERNAME")
PASSWORD = os.getenv("UDT_PASSWORD")

LOOKBACK_HOURS = float(os.getenv("LOOKBACK_HOURS", "36"))

if not USERNAME or not PASSWORD:
    raise SystemExit(
        "UDT_USERNAME and/or UDT_PASSWORD are not set. "
        "Copy .env.example to .env and fill in your real credentials."
    )

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
PDF_DIR = OUTPUT_DIR / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
}

DATE_RE = re.compile(
    r"posted .*? on (\d{1,2} \w{3} \d{4} \d{1,2}:\d{2} [ap]m)", re.IGNORECASE
)
FILE_PATH_RE = re.compile(r'var\s+file_path\s*=\s*"([^"]+)"')
```

This drops the fixed `CUTOFF_DATE`/`_cutoff_str` in favor of `LOOKBACK_HOURS`.

Replace the entire `# Main` section (from `def run():` to the end of the file) with:

```python
# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def login(session) -> None:
    resp = session.post(
        LOGIN_URL,
        data={"username": USERNAME, "password": PASSWORD},
        allow_redirects=True,
    )
    resp.raise_for_status()
    if 'id="login-form"' in resp.text:
        raise RuntimeError(
            "Login appears to have failed - check UDT_USERNAME/UDT_PASSWORD in .env, "
            "or the site may need additional hidden form fields not seen "
            "in the static HTML (check the Network tab's Form Data on submit)."
        )


def fetch_activity_messages(session) -> list[dict]:
    activity_resp = session.get(ACTIVITY_URL)
    activity_resp.raise_for_status()
    return extract_messages(activity_resp.text)


def filter_recent(messages: list[dict], lookback_hours: float) -> list[dict]:
    cutoff = datetime.now() - timedelta(hours=lookback_hours)
    filtered = [
        m for m in messages
        if dateparser.parse(m["posted_at"]) >= cutoff
    ]
    filtered.sort(key=lambda m: m["posted_at"], reverse=True)
    return filtered


def download_message_attachments(session, messages: list[dict]) -> None:
    for m in messages:
        for att in m["attachments"]:
            href = att["href"]
            if not href:
                continue
            viewer_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            try:
                viewer_resp = session.get(viewer_url)
                match = FILE_PATH_RE.search(viewer_resp.text)
                if not match:
                    att["saved_as"] = None
                    att["note"] = "Could not find file_path in viewer page"
                    continue

                file_url = match.group(1).replace("\\/", "/")
                file_resp = session.get(file_url)
                content_type = file_resp.headers.get("content-type", "")

                ext = ".pdf" if "pdf" in content_type.lower() or file_url.lower().endswith(".pdf") else ""
                if not ext and "." in file_url.rsplit("/", 1)[-1]:
                    ext = "." + file_url.rsplit(".", 1)[-1]

                safe_name = re.sub(r"[^\w\-. ]", "_", att["name"]) + ext
                (PDF_DIR / safe_name).write_bytes(file_resp.content)
                att["saved_as"] = str(PDF_DIR / safe_name)
                att["source_url"] = file_url
            except Exception as e:
                att["saved_as"] = None
                att["note"] = f"Download failed: {e}"


def fetch_recent_messages(lookback_hours: float | None = None, download_attachments: bool = False) -> list[dict]:
    """Log in, fetch the activity page, and return messages posted within
    the rolling lookback window (hours), most recent first. Raises
    RuntimeError if login fails."""
    if lookback_hours is None:
        lookback_hours = LOOKBACK_HOURS
    session = requests.Session()
    session.headers.update(HEADERS)
    login(session)
    all_messages = fetch_activity_messages(session)
    filtered = filter_recent(all_messages, lookback_hours)
    if download_attachments:
        download_message_attachments(session, filtered)
    return filtered


def run():
    filtered = fetch_recent_messages(download_attachments=True)
    if not filtered:
        print("No messages parsed in the lookback window.")
        return

    out_file = OUTPUT_DIR / f"messages_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_file.write_text(json.dumps(filtered, indent=2, ensure_ascii=False))
    print(f"Saved {len(filtered)} messages to {out_file}")
    print(f"PDFs (where successfully downloaded) are in {PDF_DIR}")


if __name__ == "__main__":
    run()
```

Also add `timedelta` to the existing `from datetime import datetime` import line at the top of the file, so it reads:

```python
from datetime import datetime, timedelta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scrape_udt.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Manual smoke test of unchanged behavior**

Run: `python scrape_udt.py` (with real `.env` credentials in place)
Expected: same behavior as before — logs in, fetches, saves `output/messages_<timestamp>.json` — just using the rolling 36h window instead of a fixed cutoff date.

---

### Task 3: WhatsApp fetcher (`fetch_whatsapp.py`)

**Files:**
- Create: `fetch_whatsapp.py`
- Test: `tests/test_fetch_whatsapp.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetch_whatsapp.py`:

```python
from datetime import datetime, timedelta


def test_parse_jsonl_skips_blank_and_invalid_lines():
    from fetch_whatsapp import parse_jsonl

    text = '{"a": 1}\n\n not json \n{"b": 2}\n'
    result = parse_jsonl(text)
    assert result == [{"a": 1}, {"b": 2}]


def test_filter_recent_includes_message_within_window():
    from fetch_whatsapp import filter_recent

    now = datetime.now().astimezone()
    recent = (now - timedelta(hours=1)).isoformat()
    messages = [{"timestamp": recent, "sender": "A", "text": "hi"}]
    result = filter_recent(messages, lookback_hours=36)
    assert len(result) == 1


def test_filter_recent_excludes_message_before_cutoff():
    from fetch_whatsapp import filter_recent

    now = datetime.now().astimezone()
    old = (now - timedelta(hours=40)).isoformat()
    messages = [{"timestamp": old, "sender": "A", "text": "hi"}]
    result = filter_recent(messages, lookback_hours=36)
    assert result == []


def test_filter_recent_skips_entries_without_timestamp():
    from fetch_whatsapp import filter_recent

    messages = [{"sender": "A", "text": "no timestamp field"}]
    result = filter_recent(messages, lookback_hours=36)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch_whatsapp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_whatsapp'`

- [ ] **Step 3: Implement `fetch_whatsapp.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_whatsapp.py -v`
Expected: PASS (4 tests)

---

### Task 4: Orchestrator (`daily_brief.py`)

**Files:**
- Create: `daily_brief.py`
- Test: `tests/test_daily_brief.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_daily_brief.py`:

```python
import daily_brief


def test_gather_captures_portal_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["error"] == "login failed"
    assert result["portal"]["messages"] == []
    assert result["whatsapp"]["error"] is None
    assert result["whatsapp"]["messages"] == []


def test_gather_returns_messages_on_success(monkeypatch):
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [{"title": "x"}])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [{"text": "y"}])

    result = daily_brief.gather()

    assert result["portal"]["messages"] == [{"title": "x"}]
    assert result["portal"]["error"] is None
    assert result["whatsapp"]["messages"] == [{"text": "y"}]
    assert result["whatsapp"]["error"] is None


def test_gather_captures_whatsapp_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("drive unreachable")

    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", failing_fetch)

    result = daily_brief.gather()

    assert result["whatsapp"]["error"] == "drive unreachable"
    assert result["portal"]["error"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_daily_brief.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'daily_brief'`

- [ ] **Step 3: Implement `daily_brief.py`**

```python
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
        result["portal"]["error"] = str(e)

    try:
        result["whatsapp"]["messages"] = fetch_recent_whatsapp_messages()
    except Exception as e:
        result["whatsapp"]["error"] = str(e)

    return result


def run():
    data = gather()
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT_PATH}")
    return data


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_daily_brief.py -v`
Expected: PASS (3 tests)

---

### Task 5: Update dependencies and `.env.example`

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Update `requirements.txt`**

Replace the full contents with:

```
requests>=2.31.0
beautifulsoup4>=4.12.0
python-dateutil>=2.8.2
python-dotenv>=1.0.0
google-api-python-client>=2.100.0
google-auth>=2.23.0
pytest>=7.4.0
```

- [ ] **Step 2: Install new dependencies**

Run: `pip install -r requirements.txt`
Expected: installs `google-api-python-client`, `google-auth`, `pytest` alongside the existing packages.

- [ ] **Step 3: Update `.env.example`**

Replace the full contents with:

```
# Copy this file to .env and fill in your real values.
# .env itself is gitignored and should never be committed.

UDT_BASE_URL=https://sarvottam.udtweb.com
UDT_USERNAME=your_username_here
UDT_PASSWORD=your_password_here

# Rolling lookback window (hours) used by both the portal and WhatsApp
# fetchers - each run looks back this far from "now", no fixed date.
LOOKBACK_HOURS=36

# Google Drive service account (for reading the WhatsApp JSONL log).
# Either an absolute path to the service account's JSON key file, or
# the raw JSON key content itself (used for the cloud-scheduled run,
# where there's no local file to point to).
GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/service-account.json

# The Drive file ID of the WhatsApp JSONL log (from its share URL).
WHATSAPP_DRIVE_FILE_ID=your_drive_file_id_here
```

- [ ] **Step 4: Verify existing tests still pass with the updated env template**

Run: `python -m pytest tests/ -v`
Expected: PASS (11 tests total across the three test files)

---

### Task 6: Claude skill (`.claude/skills/daily-school-brief/SKILL.md`)

**Files:**
- Create: `.claude/skills/daily-school-brief/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: daily-school-brief
description: Generate the daily school brief (homework, tomorrow's agenda, dress code, other reminders) from the school portal and WhatsApp group logs, and push a notification with it. Use when asked to run or generate the daily school brief, or on the scheduled evening trigger.
---

# Daily School Brief

## What this does

Combines two message sources - the school web portal and the school
WhatsApp group (captured via phone automation into a Google Drive file)
- covering roughly the last 36 hours, and produces a short brief covering:

- Homework
- Tomorrow's school agenda (events, holidays, notices)
- Tomorrow's dress code
- Other reminders

Then sends the brief as a push notification.

## Steps

1. From the project root, run:

   ```bash
   python daily_brief.py
   ```

   This writes `output/daily_brief_input.json` with two sections,
   `portal` and `whatsapp`, each having `messages` (a list) and `error`
   (a string or null).

2. Read `output/daily_brief_input.json`.

3. For each source with a non-null `error`, note it as a warning to
   include at the top of the brief (e.g. "couldn't reach school
   portal") - a failure in one source should not stop you from using
   the other source's messages.

4. If both sources have zero messages and no errors, the brief is just:
   "Nothing new from the school portal or WhatsApp group in the last day."

5. Otherwise, read through all messages from both sources and use your
   own judgment to extract (the messages are unstructured free text -
   don't pattern-match on fixed keywords):
   - **Homework**: any assignment, reading, or task mentioned for the
     child to do.
   - **Tomorrow's agenda**: events, special activities, holidays, timing
     changes, or notices that apply to tomorrow specifically (use
     today's date to work out what "tomorrow" refers to).
   - **Dress code**: any uniform/dress instructions that apply tomorrow
     (e.g. "sports day, wear house colors", "PE kit tomorrow").
   - **Other reminders**: anything else worth a parent's attention (fee
     due dates, forms to sign, items to bring) that doesn't fit the
     above.
   Omit a section entirely if there's nothing for it, rather than
   forcing an empty slot.

6. Compose the brief as plain text with short section headers.

7. Send it with the PushNotification tool (`status: "proactive"`,
   `message` = the brief text). Mobile OSes truncate long
   notifications, so keep it under ~200 characters where possible -
   lead with the most time-sensitive items (tomorrow's dress code,
   homework due tomorrow) if the full brief would run longer.
```

- [ ] **Step 2: Verify the skill is discovered**

Run (from the project root, in a Claude Code session): `/daily-school-brief` should appear as an invokable skill (or be listed when asking "what skills are available").

---

### Task 7: Phone-side setup docs (`docs/PHONE_SETUP.md`)

**Files:**
- Create: `docs/PHONE_SETUP.md`

- [ ] **Step 1: Write the setup doc**

```markdown
# Phone-Side WhatsApp Capture Setup

This captures messages from the school WhatsApp group without any
unofficial WhatsApp client or automation library - it works entirely
through Android's notification system, which WhatsApp's own app posts
to normally.

## 1. Install MacroDroid

From the Play Store. Free tier is enough for one rule.

## 2. Create the capture rule

- Trigger: **Notification Received** -> app: WhatsApp -> title/text
  filter: matches the school group's exact chat name.
- Action: **Write Text to File**, appending (not overwriting) one JSON
  line per message to a local file, e.g.
  `/storage/emulated/0/SchoolBrief/whatsapp_log.jsonl`, in this format:

  ```json
  {"timestamp": "%dtdate(yyyy-MM-dd'T'HH:mm:ssXXX)%", "sender": "%notification_title%", "text": "%notification_text%"}
  ```

  (MacroDroid's exact variable names for notification title/text and
  date formatting may differ slightly by version - check the "Local
  Variables" / "Magic Text" reference in Configure Action for the
  current equivalents.)

## 3. Install a folder-sync app

Install **Autosync for Google Drive** (or FolderSync, by MetaCtrl) from
the Play Store. Configure a sync pair:
- Local folder: `/storage/emulated/0/SchoolBrief/`
- Remote folder: a Google Drive folder, e.g. `SchoolBrief/`
- Direction: one-way, phone -> Drive
- Sync trigger: on file change (or every few minutes)

## 4. Note the Drive file's ID

Open the synced file in Google Drive on a browser; its share URL looks
like `https://drive.google.com/file/d/<FILE_ID>/view`. Copy `<FILE_ID>`
into `WHATSAPP_DRIVE_FILE_ID` in `.env` (see Task 8 for the service
account that also needs read access to this file).

## Verifying it works

Send a test message in the school WhatsApp group, wait a minute, then
check the Drive file's content updates from your Mac's browser (or via
`python fetch_whatsapp.py` once Task 8's service account is set up).
```

---

### Task 8: Google Cloud service account for Drive read access

**Files:**
- No new files - this is external setup, verified via `fetch_whatsapp.py`.

- [ ] **Step 1: Create the service account**

In Google Cloud Console: create a project (or reuse one), enable the
"Google Drive API", create a Service Account, and generate a JSON key
for it. Note the service account's email address
(`...@<project>.iam.gserviceaccount.com`).

- [ ] **Step 2: Share the Drive file with the service account**

In Google Drive, share the `whatsapp_log.jsonl` file (or its parent
folder) with the service account's email as **Viewer**.

- [ ] **Step 3: Configure local `.env`**

Set `GOOGLE_SERVICE_ACCOUNT_JSON` to the absolute path of the downloaded
JSON key file, and `WHATSAPP_DRIVE_FILE_ID` to the file ID from Task 7.

- [ ] **Step 4: Verify**

Run: `python fetch_whatsapp.py`
Expected: prints the WhatsApp messages from the last 36 hours (or
nothing, if none yet - check by sending a test message first per
Task 7's verification step).

---

### Task 9: Wire up the scheduled cloud routine

**Files:**
- No new files in this repo.

- [ ] **Step 1: Confirm the GitHub repo is reachable**

Run: `git remote -v` and confirm `origin` points at the private GitHub
repo created in Task 1. Push any local commits made in Tasks 2-8:

```bash
git add -A && git commit -m "Add WhatsApp fetcher, orchestrator, skill, and setup docs" && git push
```

- [ ] **Step 2: Create the scheduled routine**

Invoke the `schedule` skill (`/schedule`) to create a **recurring daily
routine at 7:30pm local time**. The routine's prompt should:

1. Clone or pull the private repo (using the URL from Task 1).
2. `cd` into it and `pip install -r requirements.txt`.
3. Set the required env vars for that run: `UDT_USERNAME`, `UDT_PASSWORD`,
   `GOOGLE_SERVICE_ACCOUNT_JSON` (the raw JSON key content, not a file
   path, since there's no persistent local file in the cloud sandbox),
   and `WHATSAPP_DRIVE_FILE_ID`. Supply the real values interactively
   when creating the routine - never put real secrets in this plan
   document or in any file committed to the repo.
4. Invoke the `daily-school-brief` skill (discovered automatically from
   the cloned repo's `.claude/skills/` directory) to produce and send
   the brief.

- [ ] **Step 3: Note the 7-day / durability caveat**

Confirm with the `schedule` skill's own output whether this routine is
durable (survives indefinitely, independent of any single session) or
has an expiry - the raw `CronCreate` tool used elsewhere in this
environment is session-only and auto-expires after 7 days, which would
NOT satisfy this project's goal. If `schedule`'s routines turn out to
have a similar limit, flag it back to the user rather than assuming
it's solved.

---

### Task 10: End-to-end dry run

**Files:**
- None - verification only.

- [ ] **Step 1: Local dry run**

With real `.env` credentials and Drive access configured, run:

```bash
python daily_brief.py
```

Then manually invoke the `daily-school-brief` skill in a Claude Code
session in this repo and check the generated brief against what you'd
expect for that day (real homework/agenda/dress-code content from both
sources).

- [ ] **Step 2: Cloud dry run**

Manually trigger the scheduled routine once (rather than waiting for
7:30pm) to confirm the clone -> install -> fetch -> categorize -> push
notification chain works end-to-end outside your Mac.

- [ ] **Step 3: Let it run on schedule**

Once both dry runs succeed, let the routine run naturally the next few
evenings and confirm the push notifications arrive as expected.
