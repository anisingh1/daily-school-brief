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
  36 hours) when run standalone. Downloads PDF attachments into
  `data/pdfs/`, skipping any file that's already been saved there (by
  message ID + name), so the same document isn't re-downloaded every
  run. Can be run directly (`python scrape_udt.py`), or imported
  (`fetch_recent_messages()`) for use by other scripts.
- **`fetch_whatsapp.py`** — reads WhatsApp group messages forwarded via
  phone automation into a JSONL file on Google Drive (see
  `docs/PHONE_SETUP.md`), via the Google Drive API using a service
  account, filtered to the same rolling lookback window (standalone) or
  the orchestrated pipeline's month-start cutoff.
- **`cutoff.py`** — `month_anchor()`: 2 days before the start of the
  current calendar month. Used directly for the WhatsApp fetch (its
  Drive log already retains its own full history, so re-scanning the
  current month is enough), and as `portal_archive.py`'s fallback when
  no portal cursor has been recorded yet.
- **`portal_archive.py`** — persists the portal message archive
  (`data/portal_messages.json`, deduplicated by message id) and a
  "last run" cursor (`data/last_run.json`) in this git repo. The
  orchestrated pipeline fetches only what's new since the cursor (or
  since `month_anchor()` on a fresh setup), merges it into the archive,
  and always considers the FULL archive when generating the brief — so
  nothing scraped at any point in the past is ever dropped.
- **`daily_brief.py`** — orchestrator that calls both fetchers (portal
  via `portal_archive.py`'s cutoff, WhatsApp via `cutoff.month_anchor()`),
  treating each as best-effort (one source failing doesn't block the
  other), downloads portal attachments, and writes a combined JSON
  envelope to `output/daily_brief_input.json`.
- **`render_email.py`** — pure function, `render_brief_html(data)`,
  turning the skill's structured categorization (`output/daily_brief_content.json`)
  into a polished, sectioned HTML email body. Deterministic and tested,
  so visual quality is consistent every day regardless of that day's
  content.
- **`send_email.py`** — reads `output/daily_brief_content.json`, renders
  it via `render_email.py`, and sends it as an HTML email via Gmail SMTP.
- The `daily-school-brief` Claude Code skill
  (`.claude/skills/daily-school-brief/SKILL.md`) reads that envelope,
  `Read`s any downloaded PDF attachments directly (homework/agenda/
  dress-code details are often inside the document, not just the message
  text), commits and pushes `data/` so the archive/cursor persist across
  future runs, categorizes everything into homework / tomorrow's agenda
  / dress code / other reminders, and writes `output/daily_brief_content.json`
  and runs `send_email.py` to send it as an HTML email. A scheduled cloud
  routine runs this automatically each evening.

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
   and `WHATSAPP_DRIVE_FILE_ID`, and `SMTP_USERNAME`/`SMTP_APP_PASSWORD`/
   `EMAIL_TO` for sending the brief by email (see `send_email.py`'s
   docstring for how to create a Gmail App Password).
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
- Full pipeline (writes the combined brief-input JSON, merges the portal
  archive, downloads portal attachments):
  ```
  python daily_brief.py
  ```
  After running this as part of the scheduled/automated flow, `data/`
  needs to be committed and pushed for the archive/cursor to persist —
  see the `daily-school-brief` skill, which does this automatically.

## Output

- `output/messages_<timestamp>.json` — all parsed portal messages within
  the lookback window, with title, author/date, body text, and attachment
  info (written by `scrape_udt.py`'s standalone `run()`). Not committed
  (gitignored, under `output/`).
- `output/daily_brief_input.json` — combined `{"portal": {...}, "whatsapp":
  {...}}` envelope written by `daily_brief.py`, each side having
  `messages` and `error` fields. Not committed.
- `data/portal_messages.json` — the permanent portal message archive,
  deduplicated by message id. Committed to this repo.
- `data/last_run.json` — the portal cursor (`{"last_run": "<isoformat>"}`).
  Committed to this repo.
- `data/pdfs/` — downloaded PDF (or other) attachments, named using the
  message ID and their display name in the portal. Committed to this
  repo; a file already present here is not re-downloaded.

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
- Portal messages and their attachment PDFs older than 2 calendar months
  are pruned from `data/portal_messages.json` and deleted from
  `data/pdfs/` each run (see `portal_archive.py`'s `RETENTION_MONTHS`).
  Deleting a file doesn't reclaim git history size on its own though —
  the blob still exists in past commits until a history rewrite
  (`git gc`, BFG, `git filter-repo`), so repo size still grows slowly
  over time even with pruning in place, just far more slowly than
  without it.
