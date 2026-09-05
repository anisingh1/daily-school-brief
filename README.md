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
- `output/pdfs/` — downloaded PDF (or other) attachments, named using the
  message ID and their display name in the portal. Populated by both
  standalone runs and the orchestrated pipeline; a file already present
  here is not re-downloaded.
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
