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

> Note: attempt this after Tasks 11-14 below (the cross-run cursor
> addendum), since those tasks change how `daily_brief.py` computes its
> cutoff. Task 10 as originally written still applies otherwise.

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

---

## Addendum: Cross-run cursor (revises "no persisted cursor" decision)

See the spec's "Cross-run cursor" section for the full rationale. Summary:
a Google-Drive-persisted `last_run` cursor replaces the plain 36h rolling
window for the *orchestrated* pipeline (`daily_brief.py`), falling back to
a month-anchor floor (2 days before the start of the current calendar
month) when no cursor exists yet - so a start-of-month monthly planner
PDF is never missed on a fresh setup or after a gap. Standalone script
usage (`python scrape_udt.py` / `python fetch_whatsapp.py` run directly)
is unaffected and keeps using `LOOKBACK_HOURS`.

### Task 11: Shared `google_drive.py` module + refactor `fetch_whatsapp.py`

**Files:**
- Create: `google_drive.py`
- Modify: `fetch_whatsapp.py`
- Test: `tests/test_google_drive.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_google_drive.py`:

```python
import json

import google_drive


def test_build_client_uses_file_path_branch(monkeypatch, tmp_path):
    key_file = tmp_path / "key.json"
    key_file.write_text("{}")
    calls = {}

    def fake_from_file(path, scopes):
        calls["file_path"] = path
        return "fake-creds-from-file"

    def fake_build(service, version, credentials):
        calls["credentials"] = credentials
        return "fake-client"

    monkeypatch.setattr(
        google_drive.service_account.Credentials, "from_service_account_file", fake_from_file
    )
    monkeypatch.setattr(google_drive, "build", fake_build)

    result = google_drive.build_client(str(key_file))

    assert result == "fake-client"
    assert calls["file_path"] == str(key_file)
    assert calls["credentials"] == "fake-creds-from-file"


def test_build_client_uses_raw_json_branch(monkeypatch):
    raw_json = json.dumps({"type": "service_account"})
    calls = {}

    def fake_from_info(info, scopes):
        calls["info"] = info
        return "fake-creds-from-info"

    def fake_build(service, version, credentials):
        calls["credentials"] = credentials
        return "fake-client"

    monkeypatch.setattr(
        google_drive.service_account.Credentials, "from_service_account_info", fake_from_info
    )
    monkeypatch.setattr(google_drive, "build", fake_build)

    result = google_drive.build_client(raw_json)

    assert result == "fake-client"
    assert calls["info"] == {"type": "service_account"}
    assert calls["credentials"] == "fake-creds-from-info"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_google_drive.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'google_drive'`

- [ ] **Step 3: Create `google_drive.py`**

```python
"""
Shared Google Drive API helpers: building an authenticated client from a
service account (file path or raw JSON key content), and
downloading/uploading small text files by ID.

Used by both fetch_whatsapp.py (reads the WhatsApp JSONL log) and
drive_state.py (reads/writes the cross-run cursor).
"""

import io
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]


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


def upload_text(drive_service, file_id: str, text: str) -> None:
    media = MediaIoBaseUpload(io.BytesIO(text.encode("utf-8")), mimetype="text/plain")
    drive_service.files().update(fileId=file_id, media_body=media).execute()
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_google_drive.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Refactor `fetch_whatsapp.py` to use `google_drive.py`, and add an optional `cutoff` parameter**

Replace the full contents of `fetch_whatsapp.py` with:

```python
"""
Fetches WhatsApp group messages forwarded via phone automation.

Messages are captured by a MacroDroid rule on an Android phone (see
docs/PHONE_SETUP.md) which appends one JSON line per message to a file
in a Google Drive folder. This module reads that file via the Drive API
using a service account (see google_drive.py) and filters to a rolling
lookback window, or an explicit absolute cutoff when one is provided
(used by daily_brief.py's cross-run cursor - see drive_state.py).

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

import json
import os
from datetime import datetime, timedelta

from dateutil import parser as dateparser
from dotenv import load_dotenv

import google_drive

load_dotenv()

SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
DRIVE_FILE_ID = os.getenv("WHATSAPP_DRIVE_FILE_ID")
LOOKBACK_HOURS = float(os.getenv("LOOKBACK_HOURS", "36"))


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


def filter_recent(
    messages: list[dict], lookback_hours: float | None = None, cutoff: datetime | None = None
) -> list[dict]:
    if cutoff is None:
        if lookback_hours is None:
            lookback_hours = LOOKBACK_HOURS
        cutoff = datetime.now().astimezone() - timedelta(hours=lookback_hours)
    filtered = []
    for m in messages:
        raw_ts = m.get("timestamp")
        if not raw_ts:
            continue
        try:
            ts = dateparser.parse(raw_ts)
        except (ValueError, TypeError, OverflowError):
            continue
        if ts.tzinfo is None:
            ts = ts.astimezone()
        if ts >= cutoff:
            filtered.append(m)
    filtered.sort(key=lambda m: dateparser.parse(m["timestamp"]).astimezone())
    return filtered


def fetch_recent_whatsapp_messages(
    lookback_hours: float | None = None, cutoff: datetime | None = None
) -> list[dict]:
    if not SERVICE_ACCOUNT_JSON or not DRIVE_FILE_ID:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON and/or WHATSAPP_DRIVE_FILE_ID are not set."
        )
    drive_service = google_drive.build_client(SERVICE_ACCOUNT_JSON)
    text = google_drive.download_text(drive_service, DRIVE_FILE_ID)
    messages = parse_jsonl(text)
    return filter_recent(messages, lookback_hours=lookback_hours, cutoff=cutoff)


if __name__ == "__main__":
    for msg in fetch_recent_whatsapp_messages():
        print(msg)
```

This removes `fetch_whatsapp.py`'s own `_drive_client`/`download_jsonl_text`
(now in `google_drive.py`) and its own `SCOPES` (now `google_drive.SCOPES`,
broadened from `drive.readonly` to full `drive` access, needed because
`drive_state.py` in Task 12 writes to a Drive file with the same service
account). Per-file access is still governed by Drive sharing permissions
(Viewer vs Editor), not by this OAuth scope alone.

- [ ] **Step 6: Run the full suite to verify nothing broke**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all existing tests, e.g. `test_fetch_whatsapp.py`'s 7
tests, plus the 2 new `test_google_drive.py` tests — no regressions from
the refactor, since `parse_jsonl`/`filter_recent`'s existing behavior for
the `lookback_hours` path is unchanged, only the internal Drive-client
wiring moved).

- [ ] **Step 7: Add a test for the new `cutoff` override path**

Add `timedelta` to the existing `from datetime import datetime, timedelta`
import line at the top of `tests/test_fetch_whatsapp.py` (it currently
only imports `datetime`), then add this test:

```python
def test_filter_recent_uses_explicit_cutoff_over_lookback_hours():
    from fetch_whatsapp import filter_recent

    cutoff = datetime(2026, 9, 4, 12, 0, 0).astimezone()
    just_after = (cutoff + timedelta(minutes=1)).isoformat()
    just_before = (cutoff - timedelta(minutes=1)).isoformat()
    messages = [
        {"timestamp": just_after, "sender": "A", "text": "in"},
        {"timestamp": just_before, "sender": "A", "text": "out"},
    ]
    # lookback_hours=1000 would normally include both if it were used -
    # confirming cutoff, not lookback_hours, governs the result.
    result = filter_recent(messages, lookback_hours=1000, cutoff=cutoff)
    assert [m["text"] for m in result] == ["in"]
```

Run: `.venv/bin/python -m pytest tests/test_fetch_whatsapp.py -v`
Expected: PASS (8 tests)

---

### Task 12: New `drive_state.py` module (cross-run cursor + month-anchor fallback)

**Files:**
- Create: `drive_state.py`
- Test: `tests/test_drive_state.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_drive_state.py`:

```python
import json
from datetime import datetime, timedelta

import drive_state


def test_month_anchor_is_two_days_before_month_start():
    today = datetime(2026, 9, 15, 12, 30)
    result = drive_state.month_anchor(today)
    assert result == datetime(2026, 8, 30, 0, 0, 0)


def test_month_anchor_handles_january_rollover():
    today = datetime(2026, 1, 10)
    result = drive_state.month_anchor(today)
    assert result == datetime(2025, 12, 30, 0, 0, 0)


def test_read_last_run_returns_none_when_not_configured(monkeypatch):
    monkeypatch.setattr(drive_state, "SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(drive_state, "STATE_DRIVE_FILE_ID", None)
    assert drive_state.read_last_run() is None


def test_read_last_run_returns_none_for_empty_state_file(monkeypatch):
    monkeypatch.setattr(drive_state, "SERVICE_ACCOUNT_JSON", "fake")
    monkeypatch.setattr(drive_state, "STATE_DRIVE_FILE_ID", "fake-id")
    monkeypatch.setattr(drive_state.google_drive, "build_client", lambda sa: "client")
    monkeypatch.setattr(drive_state.google_drive, "download_text", lambda client, fid: "{}")
    assert drive_state.read_last_run() is None


def test_read_last_run_parses_saved_timestamp(monkeypatch):
    monkeypatch.setattr(drive_state, "SERVICE_ACCOUNT_JSON", "fake")
    monkeypatch.setattr(drive_state, "STATE_DRIVE_FILE_ID", "fake-id")
    monkeypatch.setattr(drive_state.google_drive, "build_client", lambda sa: "client")
    monkeypatch.setattr(
        drive_state.google_drive,
        "download_text",
        lambda client, fid: '{"last_run": "2026-09-04T19:30:00"}',
    )
    assert drive_state.read_last_run() == datetime(2026, 9, 4, 19, 30, 0)


def test_save_last_run_uploads_json(monkeypatch):
    monkeypatch.setattr(drive_state, "SERVICE_ACCOUNT_JSON", "fake")
    monkeypatch.setattr(drive_state, "STATE_DRIVE_FILE_ID", "fake-id")
    monkeypatch.setattr(drive_state.google_drive, "build_client", lambda sa: "client")
    uploaded = {}

    def fake_upload(client, file_id, text):
        uploaded["file_id"] = file_id
        uploaded["text"] = text

    monkeypatch.setattr(drive_state.google_drive, "upload_text", fake_upload)

    drive_state.save_last_run(datetime(2026, 9, 5, 18, 0, 0))

    assert uploaded["file_id"] == "fake-id"
    assert json.loads(uploaded["text"]) == {"last_run": "2026-09-05T18:00:00"}


def test_save_last_run_noop_when_not_configured(monkeypatch):
    monkeypatch.setattr(drive_state, "SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(drive_state, "STATE_DRIVE_FILE_ID", None)
    drive_state.save_last_run(datetime.now())  # must not raise


def test_compute_cutoff_uses_last_run_when_present(monkeypatch):
    saved = datetime(2026, 9, 4, 19, 30)
    monkeypatch.setattr(drive_state, "read_last_run", lambda: saved)
    assert drive_state.compute_cutoff() == saved


def test_compute_cutoff_falls_back_to_month_anchor_when_absent(monkeypatch):
    monkeypatch.setattr(drive_state, "read_last_run", lambda: None)
    assert drive_state.compute_cutoff() == drive_state.month_anchor()


def test_compute_cutoff_falls_back_to_month_anchor_on_read_error(monkeypatch):
    def boom():
        raise RuntimeError("drive down")

    monkeypatch.setattr(drive_state, "read_last_run", boom)
    assert drive_state.compute_cutoff() == drive_state.month_anchor()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_drive_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drive_state'`

- [ ] **Step 3: Implement `drive_state.py`**

```python
"""
Persists a "last run" cursor for the orchestrated daily-brief pipeline
(daily_brief.py) on Google Drive, so runs only need to look back as far
as the last successful run instead of re-fetching a fixed window every
time.

Falls back to a month-anchor floor (2 days before the start of the
current calendar month) when no cursor has been saved yet, so a
start-of-month monthly planner PDF is never missed on a fresh setup or
after a gap.

Uses the same Google Drive service account as fetch_whatsapp.py (see
google_drive.py), but the state file needs to be shared with it as
Editor (not just Viewer), since this module writes to it.

SETUP:
    - Create an empty Drive file (e.g. containing `{}`) for the cursor.
    - Share it with the service account's email as Editor.
    - Set STATE_DRIVE_FILE_ID to that file's Drive file ID in .env.
"""

import json
import os
from datetime import datetime, timedelta

from dateutil import parser as dateparser
from dotenv import load_dotenv

import google_drive

load_dotenv()

SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
STATE_DRIVE_FILE_ID = os.getenv("STATE_DRIVE_FILE_ID")


def month_anchor(today: datetime | None = None) -> datetime:
    """2 days before the start of the current calendar month."""
    if today is None:
        today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start - timedelta(days=2)


def read_last_run() -> datetime | None:
    if not SERVICE_ACCOUNT_JSON or not STATE_DRIVE_FILE_ID:
        return None
    drive_service = google_drive.build_client(SERVICE_ACCOUNT_JSON)
    text = google_drive.download_text(drive_service, STATE_DRIVE_FILE_ID)
    data = json.loads(text) if text.strip() else {}
    raw = data.get("last_run")
    if not raw:
        return None
    return dateparser.parse(raw)


def save_last_run(dt: datetime) -> None:
    if not SERVICE_ACCOUNT_JSON or not STATE_DRIVE_FILE_ID:
        return
    try:
        drive_service = google_drive.build_client(SERVICE_ACCOUNT_JSON)
        google_drive.upload_text(
            drive_service, STATE_DRIVE_FILE_ID, json.dumps({"last_run": dt.isoformat()})
        )
    except Exception as e:
        print(f"Warning: failed to save last_run cursor: {e}")


def compute_cutoff() -> datetime:
    try:
        last_run = read_last_run()
    except Exception as e:
        print(f"Warning: failed to read last_run cursor, falling back to month anchor: {e}")
        last_run = None
    if last_run is not None:
        return last_run
    return month_anchor()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_drive_state.py -v`
Expected: PASS (10 tests)

---

### Task 13: Optional absolute `cutoff` parameter in `scrape_udt.py`

**Files:**
- Modify: `scrape_udt.py`
- Test: `tests/test_scrape_udt.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scrape_udt.py` (uses the existing `_msg` helper's
sibling pattern, but builds messages directly since it needs to anchor
to an explicit cutoff rather than an offset from `datetime.now()`):

```python
def test_filter_recent_uses_explicit_cutoff_over_lookback_hours():
    from scrape_udt import filter_recent

    cutoff = datetime(2026, 9, 4, 12, 0, 0)
    messages = [
        {"id": "in", "title": "t", "posted_at": (cutoff + timedelta(hours=1)).isoformat(), "body": "b", "attachments": []},
        {"id": "out", "title": "t", "posted_at": (cutoff - timedelta(hours=1)).isoformat(), "body": "b", "attachments": []},
    ]
    # lookback_hours=1000 would normally include both if it were used -
    # confirming cutoff, not lookback_hours, governs the result.
    result = filter_recent(messages, lookback_hours=1000, cutoff=cutoff)
    assert [m["id"] for m in result] == ["in"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_scrape_udt.py -v`
Expected: FAIL — `TypeError: filter_recent() got an unexpected keyword argument 'cutoff'`

- [ ] **Step 3: Add the `cutoff` parameter**

In `scrape_udt.py`, replace the `filter_recent` and `fetch_recent_messages`
functions with:

```python
def filter_recent(
    messages: list[dict], lookback_hours: float | None = None, cutoff: datetime | None = None
) -> list[dict]:
    if cutoff is None:
        if lookback_hours is None:
            lookback_hours = LOOKBACK_HOURS
        cutoff = datetime.now() - timedelta(hours=lookback_hours)
    filtered = [
        m for m in messages
        if dateparser.parse(m["posted_at"]) >= cutoff
    ]
    filtered.sort(key=lambda m: m["posted_at"], reverse=True)
    return filtered


def fetch_recent_messages(
    lookback_hours: float | None = None,
    cutoff: datetime | None = None,
    download_attachments: bool = False,
) -> list[dict]:
    """Log in, fetch the activity page, and return messages posted since
    `cutoff` if given, else within the rolling lookback window (hours),
    most recent first. Raises RuntimeError if login fails."""
    session = requests.Session()
    session.headers.update(HEADERS)
    login(session)
    all_messages = fetch_activity_messages(session)
    if not all_messages:
        print("No messages parsed - the page structure may differ from what "
              "was inspected, or login didn't actually succeed. Inspect "
              "activity_resp.text manually if this happens.")
    filtered = filter_recent(all_messages, lookback_hours=lookback_hours, cutoff=cutoff)
    if download_attachments:
        download_message_attachments(session, filtered)
    return filtered
```

(The only behavioral change from the current version: `fetch_recent_messages`
no longer resolves `lookback_hours` itself — that resolution now happens
once, inside `filter_recent`, and `fetch_recent_messages` just passes both
parameters straight through.)

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all `test_scrape_udt.py` tests, including the new one —
no regressions, since `filter_recent(messages, lookback_hours=36)`, the
form all existing tests use, still resolves exactly as before).

---

### Task 14: Wire the cursor into `daily_brief.py`, plus `.env.example`/README updates

**Files:**
- Modify: `daily_brief.py`
- Modify: `tests/test_daily_brief.py`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update `tests/test_daily_brief.py`**

Replace the full contents with:

```python
import json
from datetime import datetime

import daily_brief


def test_gather_captures_portal_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["error"] == "RuntimeError: login failed"
    assert result["portal"]["messages"] == []
    assert result["whatsapp"]["error"] is None
    assert result["whatsapp"]["messages"] == []


def test_gather_returns_messages_on_success(monkeypatch):
    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
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

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", failing_fetch)

    result = daily_brief.gather()

    assert result["whatsapp"]["error"] == "RuntimeError: drive unreachable"
    assert result["portal"]["error"] is None


def test_gather_saves_cursor_only_when_both_sources_succeed(monkeypatch):
    saved = {}
    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: saved.setdefault("called_with", dt))
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    daily_brief.gather()

    assert "called_with" in saved


def test_gather_does_not_save_cursor_when_a_source_fails(monkeypatch):
    saved = {}

    def failing_fetch(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: saved.setdefault("called_with", dt))
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    daily_brief.gather()

    assert "called_with" not in saved


def test_run_writes_output_file(monkeypatch, tmp_path):
    fixed_result = {
        "portal": {"messages": [], "error": None},
        "whatsapp": {"messages": [], "error": None},
    }
    monkeypatch.setattr(daily_brief, "gather", lambda: fixed_result)
    out_path = tmp_path / "out.json"
    monkeypatch.setattr(daily_brief, "OUTPUT_PATH", out_path)

    result = daily_brief.run()

    assert out_path.exists()
    assert json.loads(out_path.read_text()) == result == fixed_result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_daily_brief.py -v`
Expected: FAIL — `AttributeError` (or similar) since `daily_brief` doesn't
yet have `compute_cutoff`/`save_last_run` attributes to monkeypatch.

- [ ] **Step 3: Update `daily_brief.py`**

Replace the full contents with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_daily_brief.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the entire suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all tests across every test file — this is the full
regression check after touching 4 production files across these 4 tasks).

- [ ] **Step 6: Update `.env.example`**

Add a new line documenting `STATE_DRIVE_FILE_ID`, placed right after the
existing `WHATSAPP_DRIVE_FILE_ID` line:

```
# The Drive file ID of the cross-run cursor state file (a small JSON
# file containing {"last_run": "<isoformat>"}). Must be shared with the
# service account as Editor (not just Viewer) since it's written to.
STATE_DRIVE_FILE_ID=your_state_file_id_here
```

- [ ] **Step 7: Update `README.md`**

In the "Components" section, add a bullet after the `daily_brief.py`
bullet describing the cursor behavior, e.g.:

```
- **`drive_state.py`** — persists a small `last_run` cursor on Google
  Drive between orchestrated runs, so `daily_brief.py` only looks back as
  far as the last successful run instead of a fixed window. Falls back
  to 2 days before the start of the current calendar month when no
  cursor exists yet (fresh setup, or after a gap), so a start-of-month
  monthly planner PDF is never missed.
```

Also add `STATE_DRIVE_FILE_ID` to the "Setup" section's list of `.env`
values to fill in, alongside the existing `GOOGLE_SERVICE_ACCOUNT_JSON`
and `WHATSAPP_DRIVE_FILE_ID` mention.

- [ ] **Step 8: Commit**

Commit all changes from Tasks 11-14 (or commit incrementally per task,
whichever this session already did) with descriptive messages, normal
`git add`/`git commit`/`git push`, no force-push, no amend.

---

## Addendum 2: Month-start cutoff replaces the persisted cursor; PDFs read directly

See the spec's "Month-start cutoff, not a persisted cursor" section for
full rationale. Summary: the Tasks 11-14 cursor design had a real flaw —
content posted once (e.g. a monthly planner PDF posted on day 1,
containing information relevant to day 5) would drop out of
consideration forever once the cursor advanced past the day it was
posted, even though it had already been fetched/downloaded once. Fix:
drop the persisted cursor entirely; the orchestrated pipeline always
uses a fixed "2 days before start of current month" cutoff, since the
portal page and WhatsApp Drive log both already retain their own full
history and re-fetching the whole month is cheap. The only real cost to
avoid repeating - downloading the same PDF attachment every day - is
solved locally with a skip-if-already-downloaded check, not a cursor.
Separately: portal attachments are now downloaded in the orchestrated
pipeline too (previously `download_attachments=False`), and the skill
`Read`s them directly, since homework/agenda/dress-code details are
often inside the PDF, not the message body text.

### Task 15: Replace `drive_state.py` with `cutoff.py`; enable + dedupe PDF downloads

**Files:**
- Create: `cutoff.py`
- Delete: `drive_state.py`
- Test: Create `tests/test_cutoff.py`; Delete `tests/test_drive_state.py`
- Modify: `scrape_udt.py`
- Modify: `tests/test_scrape_udt.py`
- Modify: `daily_brief.py`
- Modify: `tests/test_daily_brief.py`

- [ ] **Step 1: Write the failing tests for `cutoff.py`**

Create `tests/test_cutoff.py`:

```python
from datetime import datetime

import cutoff


def test_month_anchor_is_two_days_before_month_start():
    today = datetime(2026, 9, 15, 12, 30)
    result = cutoff.month_anchor(today)
    assert result == datetime(2026, 8, 30, 0, 0, 0)


def test_month_anchor_handles_january_rollover():
    today = datetime(2026, 1, 10)
    result = cutoff.month_anchor(today)
    assert result == datetime(2025, 12, 30, 0, 0, 0)


def test_compute_cutoff_returns_month_anchor():
    assert cutoff.compute_cutoff() == cutoff.month_anchor()
```

Delete `tests/test_drive_state.py` (its tests are superseded — there's no
more persisted state to test).

- [ ] **Step 2: Run the new test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cutoff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cutoff'`

- [ ] **Step 3: Create `cutoff.py`, delete `drive_state.py`**

Create `cutoff.py`:

```python
"""
Computes the cutoff used by the orchestrated daily-brief pipeline
(daily_brief.py) for both the portal and WhatsApp fetchers: always 2 days
before the start of the current calendar month.

The portal's activity page and the WhatsApp Drive log both already
retain their own full history (nothing is deleted), so there's no need
to persist a "last run" cursor between runs - re-fetching and
re-filtering the whole month is cheap. The only genuinely expensive
thing to avoid repeating is downloading the same PDF attachment twice;
that's handled separately in scrape_udt.py by skipping a download if the
target file already exists on disk.

Using "start of month minus 2 days" (rather than exactly day 1) gives
slack for a message posted right at the month boundary and guards
against clock/timezone edge cases.
"""

from datetime import datetime, timedelta


def month_anchor(today: datetime | None = None) -> datetime:
    """2 days before the start of the current calendar month."""
    if today is None:
        today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start - timedelta(days=2)


def compute_cutoff() -> datetime:
    return month_anchor()
```

Delete `drive_state.py` entirely — it's fully superseded by `cutoff.py`.

- [ ] **Step 4: Run the new test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cutoff.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing tests for PDF dedupe in `scrape_udt.py`**

Add to `tests/test_scrape_udt.py`:

```python
def test_download_message_attachments_skips_already_downloaded_file(tmp_path, monkeypatch):
    import scrape_udt

    monkeypatch.setattr(scrape_udt, "PDF_DIR", tmp_path)
    existing_file = tmp_path / "Homework.pdf"
    existing_file.write_bytes(b"old content")

    class FakeViewerResponse:
        text = 'var file_path = "http://example.com/files/homework.pdf";'

    class FakeSession:
        def __init__(self):
            self.get_calls = []

        def get(self, url):
            self.get_calls.append(url)
            return FakeViewerResponse()

    session = FakeSession()
    messages = [{"attachments": [{"name": "Homework", "href": "/viewer/1"}]}]

    scrape_udt.download_message_attachments(session, messages)

    assert messages[0]["attachments"][0]["saved_as"] == str(existing_file)
    assert messages[0]["attachments"][0]["note"] == "Already downloaded"
    assert existing_file.read_bytes() == b"old content"
    assert len(session.get_calls) == 1


def test_download_message_attachments_downloads_new_file(tmp_path, monkeypatch):
    import scrape_udt

    monkeypatch.setattr(scrape_udt, "PDF_DIR", tmp_path)

    class FakeViewerResponse:
        text = 'var file_path = "http://example.com/files/homework.pdf";'

    class FakeFileResponse:
        content = b"pdf bytes"

    class FakeSession:
        def get(self, url):
            if "viewer" in url:
                return FakeViewerResponse()
            return FakeFileResponse()

    messages = [{"attachments": [{"name": "Homework", "href": "/viewer/1"}]}]

    scrape_udt.download_message_attachments(FakeSession(), messages)

    saved_path = tmp_path / "Homework.pdf"
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"pdf bytes"
    assert messages[0]["attachments"][0]["saved_as"] == str(saved_path)
```

- [ ] **Step 6: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scrape_udt.py -v`
Expected: FAIL — `AssertionError` on the "skips already downloaded"
test's `len(session.get_calls) == 1` (current code always makes 2 calls,
fetching the file even when it already exists on disk), since dedupe
doesn't exist yet.

- [ ] **Step 7: Add dedupe to `download_message_attachments`**

Replace `download_message_attachments` in `scrape_udt.py` with:

```python
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
                ext = ""
                if "." in file_url.rsplit("/", 1)[-1]:
                    ext = "." + file_url.rsplit(".", 1)[-1]
                safe_name = re.sub(r"[^\w\-. ]", "_", att["name"]) + ext
                dest_path = PDF_DIR / safe_name

                if dest_path.exists():
                    att["saved_as"] = str(dest_path)
                    att["source_url"] = file_url
                    att["note"] = "Already downloaded"
                    continue

                file_resp = session.get(file_url)
                dest_path.write_bytes(file_resp.content)
                att["saved_as"] = str(dest_path)
                att["source_url"] = file_url
            except Exception as e:
                att["saved_as"] = None
                att["note"] = f"Download failed: {e}"
```

This drops the old content-type-based extension sniffing (which required
fetching the file first just to inspect its `content-type` header) in
favor of a URL-based extension guess alone, computed *before* deciding
whether to download at all — this is what makes the dedupe check
possible without an extra network round-trip for files that already
exist.

- [ ] **Step 8: Run the full suite to verify everything passes**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all tests, including the 2 new dedupe tests and the 3
new `test_cutoff.py` tests)

- [ ] **Step 9: Write the failing test for `daily_brief.py`'s new wiring**

Replace `tests/test_daily_brief.py` in full with:

```python
import json

import daily_brief


def test_gather_captures_portal_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["error"] == "RuntimeError: login failed"
    assert result["portal"]["messages"] == []
    assert result["whatsapp"]["error"] is None
    assert result["whatsapp"]["messages"] == []


def test_gather_returns_messages_on_success(monkeypatch):
    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
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

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", failing_fetch)

    result = daily_brief.gather()

    assert result["whatsapp"]["error"] == "RuntimeError: drive unreachable"
    assert result["portal"]["error"] is None


def test_gather_downloads_portal_attachments_with_shared_cutoff(monkeypatch):
    calls = {}

    def fake_fetch(**kwargs):
        calls.update(kwargs)
        return []

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", fake_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    daily_brief.gather()

    assert calls["download_attachments"] is True
    assert calls["cutoff"] == "fixed-cutoff"


def test_run_writes_output_file(monkeypatch, tmp_path):
    fixed_result = {
        "portal": {"messages": [], "error": None},
        "whatsapp": {"messages": [], "error": None},
    }
    monkeypatch.setattr(daily_brief, "gather", lambda: fixed_result)
    out_path = tmp_path / "out.json"
    monkeypatch.setattr(daily_brief, "OUTPUT_PATH", out_path)

    result = daily_brief.run()

    assert out_path.exists()
    assert json.loads(out_path.read_text()) == result == fixed_result
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_daily_brief.py -v`
Expected: FAIL — `AttributeError` (`daily_brief` has no attribute
`compute_cutoff`; it currently imports `compute_cutoff`/`save_last_run`
from `drive_state`, which this task deletes).

- [ ] **Step 11: Update `daily_brief.py`**

Replace the full contents with:

```python
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
```

Note: this drops the `save_last_run` call and the "only advance the
cursor when both sources succeed" logic entirely — there's no cursor to
advance anymore.

- [ ] **Step 12: Run the full suite to verify everything passes**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all tests across every file)

- [ ] **Step 13: Commit**

Commit with a descriptive message (normal `git add`/`git commit`/`git
push`, no force-push, no amend). Make sure `git add` picks up the
deletion of `drive_state.py` and `tests/test_drive_state.py` (use `git
add -A` or explicitly `git rm` them if they don't show up in a plain
`git add .`).

---

### Task 16: Skill reads PDFs directly; `google_drive.py` reverts to read-only; docs updated

**Files:**
- Modify: `.claude/skills/daily-school-brief/SKILL.md`
- Modify: `google_drive.py`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update the skill to read PDF attachments**

Replace the full contents of `.claude/skills/daily-school-brief/SKILL.md`
with:

```markdown
---
name: daily-school-brief
description: Generate the daily school brief (homework, tomorrow's agenda, dress code, other reminders) from the school portal and WhatsApp group logs, and push a notification with it. Use when asked to run or generate the daily school brief, or on the scheduled evening trigger.
---

# Daily School Brief

## What this does

Combines two message sources - the school web portal and the school
WhatsApp group (captured via phone automation into a Google Drive file)
- covering everything since the start of the current calendar month, and
produces a short brief covering:

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

   The project root is the directory containing `daily_brief.py`,
   `scrape_udt.py`, and `fetch_whatsapp.py`. If you're not already
   there (e.g. in a fresh clone on a scheduled cloud routine), `cd`
   into it first before running the command.

   This writes `output/daily_brief_input.json` with two sections,
   `portal` and `whatsapp`, each having `messages` (a list) and `error`
   (a string or null). Portal messages may include an `attachments`
   list; a downloaded attachment has a `saved_as` local file path.

   If `python daily_brief.py` fails to run (crashes, `python` not
   found, etc.) or `output/daily_brief_input.json` does not exist
   afterward, don't stop silently - send a push notification saying
   the daily brief couldn't be generated, including a short reason if
   one is available, and stop there.

2. Read `output/daily_brief_input.json` (path relative to the project
   root from step 1 - this only works if you're actually in that
   directory when you run step 1).

3. For each portal message that has an attachment with a `saved_as`
   path, `Read` that file directly (Claude Code's `Read` tool handles
   PDFs natively). Homework, agenda, and dress-code details are often
   inside the document itself - a monthly planner PDF, for instance -
   rather than in the message body text, so don't rely on the body
   text alone when an attachment is present.

4. For each source with a non-null `error`, note it as a warning to
   include at the top of the brief (e.g. "couldn't reach school
   portal") - a failure in one source should not stop you from using
   the other source's messages.

5. If both sources have zero messages and no errors, the brief is just:
   "Nothing new from the school portal or WhatsApp group this month."

6. Otherwise, read through all messages (and any attachment content
   read in step 3) from both sources and use your own judgment to
   extract (the content is unstructured free text - don't pattern-match
   on fixed keywords):
   - **Homework**: any assignment, reading, or task mentioned for the
     child to do.
   - **Tomorrow's agenda**: events, special activities, holidays, timing
     changes, or notices that apply to tomorrow specifically (use
     today's date in IST - India Standard Time, UTC+5:30, the school's
     timezone - to work out what "tomorrow" refers to; do not use the
     local timezone of the machine or sandbox running this skill).
     Content posted earlier in the month (e.g. a monthly planner) that
     happens to apply to tomorrow counts just as much as something
     posted today.
   - **Dress code**: any uniform/dress instructions that apply tomorrow
     (e.g. "sports day, wear house colors", "PE kit tomorrow").
   - **Other reminders**: anything else worth a parent's attention (fee
     due dates, forms to sign, items to bring) that doesn't fit the
     above.
   Omit a section entirely if there's nothing for it, rather than
   forcing an empty slot.

7. Compose the brief as plain text with short section headers. This is
   a draft/internal step - it's fine for this draft to span multiple
   lines and sections.

8. Condense that draft into the actual notification message: the
   PushNotification tool requires a single line of plain text with no
   markdown formatting. Send it with `status: "proactive"`, `message`
   = the condensed brief. Mobile OSes truncate long notifications, so
   keep the single line under ~200 characters where possible - lead
   with the most time-sensitive items (tomorrow's dress code, homework
   due tomorrow) first, since anything after that point may get cut
   off if the full brief would run longer.
```

- [ ] **Step 2: Sanity-check the frontmatter still parses**

Run: `.venv/bin/python -c "import yaml; print(yaml.safe_load(open('.claude/skills/daily-school-brief/SKILL.md').read().split('---')[1]))"`
Expected: prints a dict with `name`/`description` keys, no errors. (If
`yaml` isn't installed in the venv, `.venv/bin/pip install pyyaml` first
just for this check — it's not a project dependency, only used here to
validate the frontmatter.)

- [ ] **Step 3: Revert `google_drive.py` to read-only, remove dead code**

Nothing in the codebase writes to Google Drive anymore (there's no more
state file to update). Replace the full contents of `google_drive.py`
with:

```python
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
```

This drops `upload_text` (no longer called anywhere) and the `MediaIoBaseUpload`
import, and narrows `SCOPES` back to `drive.readonly`.

- [ ] **Step 4: Run the full suite to verify nothing broke**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all tests — `tests/test_google_drive.py`'s 2 tests only
exercise `build_client`, unaffected by `upload_text`'s removal).

- [ ] **Step 5: Update `.env.example`**

Replace the full contents with:

```
# Copy this file to .env and fill in your real values.
# .env itself is gitignored and should never be committed.

UDT_BASE_URL=https://sarvottam.udtweb.com
UDT_USERNAME=your_username_here
UDT_PASSWORD=your_password_here

# Rolling lookback window (hours) used by both fetchers when run
# standalone (python scrape_udt.py / python fetch_whatsapp.py directly).
# The orchestrated pipeline (daily_brief.py) ignores this and always
# uses a month-start cutoff instead (see cutoff.py).
LOOKBACK_HOURS=36

# Google Drive service account (for reading the WhatsApp JSONL log).
# Either an absolute path to the service account's JSON key file, or
# the raw JSON key content itself (used for the cloud-scheduled run,
# where there's no local file to point to).
GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/service-account.json

# The Drive file ID of the WhatsApp JSONL log (from its share URL).
WHATSAPP_DRIVE_FILE_ID=your_drive_file_id_here
```

(This removes the `STATE_DRIVE_FILE_ID` block — there's no more state
file to configure.)

- [ ] **Step 6: Update `README.md`**

Replace the full contents with:

```markdown
# Daily School Brief

Pulls together messages from the school web portal and (via phone-forwarded
messages synced through Google Drive) the school WhatsApp group, and
produces a daily brief covering homework, tomorrow's agenda, tomorrow's
dress code, and other reminders.

See `docs/superpowers/specs/2026-09-05-daily-school-brief-design.md` for the
full design and `docs/superpowers/plans/2026-09-05-daily-school-brief.md`
for the implementation plan and current build status.

## Components

- **`scrape_udt.py`** — logs into the UDT eSchool parent portal, fetches
  the activity/messages page, parses each message (title, author, date,
  body, PDF attachments), and filters to a rolling lookback window (default
  36 hours) when run standalone. Downloads PDF attachments, skipping any
  file that's already been saved under `output/pdfs/` (by name), so the
  same document isn't re-downloaded every run. Can be run directly
  (`python scrape_udt.py`), or imported (`fetch_recent_messages()`) for
  use by other scripts.
- **`fetch_whatsapp.py`** — reads WhatsApp group messages forwarded via
  phone automation into a JSONL file on Google Drive (see
  `docs/PHONE_SETUP.md`), via the Google Drive API using a service
  account, filtered to the same rolling lookback window (standalone) or
  the orchestrated pipeline's month-start cutoff.
- **`cutoff.py`** — computes the cutoff used by the orchestrated pipeline:
  2 days before the start of the current calendar month, every run (not
  an advancing cursor). The portal page and the WhatsApp Drive log both
  already retain their own full history, so re-fetching the whole month
  is cheap and nothing posted earlier in the month is ever missed, no
  matter how many days later it turns out to be relevant.
- **`daily_brief.py`** — orchestrator that calls both fetchers with that
  shared cutoff, treating each as best-effort (one source failing doesn't
  block the other), downloads portal attachments, and writes a combined
  JSON envelope to `output/daily_brief_input.json`.
- The `daily-school-brief` Claude Code skill
  (`.claude/skills/daily-school-brief/SKILL.md`) reads that envelope,
  `Read`s any downloaded PDF attachments directly (homework/agenda/
  dress-code details are often inside the document, not just the message
  text), categorizes everything into homework / tomorrow's agenda /
  dress code / other reminders, and sends a push notification with the
  brief. A scheduled cloud routine runs this automatically each evening.

## Setup

1. Create a virtual environment (recommended, optional):
   ```
   python3 -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your credentials:
   ```
   cp .env.example .env
   ```
   Then edit `.env` and fill in your real `UDT_USERNAME`, `UDT_PASSWORD`,
   desired `LOOKBACK_HOURS` (default 36, only used for standalone runs),
   and — once the WhatsApp side is set up — `GOOGLE_SERVICE_ACCOUNT_JSON`
   and `WHATSAPP_DRIVE_FILE_ID`.
   **Never commit `.env`** - it's already in `.gitignore`.

## Run

- Portal scraper only (saves messages + downloads PDFs):
  ```
  python scrape_udt.py
  ```
- WhatsApp fetcher only (prints recent messages):
  ```
  python fetch_whatsapp.py
  ```
- Full pipeline (writes the combined brief-input JSON, downloads portal
  attachments, uses the month-start cutoff):
  ```
  python daily_brief.py
  ```

## Output

- `output/messages_<timestamp>.json` — all parsed portal messages within
  the lookback window, with title, author/date, body text, and attachment
  info (written by `scrape_udt.py`'s standalone `run()`).
- `output/pdfs/` — downloaded PDF (or other) attachments, named after
  their display name in the portal. Populated by both standalone runs and
  the orchestrated pipeline; a file already present here is not
  re-downloaded.
- `output/daily_brief_input.json` — combined `{"portal": {...}, "whatsapp":
  {...}}` envelope written by `daily_brief.py`, each side having
  `messages` and `error` fields.

## Notes

- All portal messages currently load on a single page load (no pagination
  or infinite-scroll fetching) — if the school portal changes this in the
  future, the script will silently only see what's in that first page
  load and may need extending.
- Portal login is a plain form POST to `/Logins/index` with `username`/
  `password` fields — if the school changes their login page (adds a
  CSRF token, captcha, etc.) this script will need updating to match.
- PDF attachments are fetched by following each attachment's viewer page
  and extracting the real file URL from an embedded `file_path` JS
  variable, then downloading that URL directly (skipped if already
  downloaded).
- WhatsApp messages are captured entirely through Android's normal
  notification system (via phone automation), not through any unofficial
  WhatsApp client library — see the design spec for why.
```

- [ ] **Step 7: Commit**

Commit with a descriptive message (normal `git add`/`git commit`/`git
push`, no force-push, no amend).
