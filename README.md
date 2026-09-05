# UDT eSchool Portal Scraper

Logs into the UDT eSchool parent portal, fetches the activity/messages
page, parses each message (title, author, date, body, PDF attachments),
filters by date, and downloads any attached PDFs.

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
   and desired `CUTOFF_DATE`. **Never commit `.env`** - it's already in
   `.gitignore`.

## Run

```
python scrape_udt.py
```

## Output

- `output/messages_<timestamp>.json` — all parsed messages on/after your
  cutoff date, with title, author/date, body text, and attachment info.
- `output/pdfs/` — downloaded PDF (or other) attachments, named after
  their display name in the portal.

## Notes

- All messages currently load on a single page load (no pagination or
  infinite-scroll fetching) — if the school portal changes this in the
  future, the script will silently only see what's in that first page
  load and may need extending.
- Login is a plain form POST to `/Logins/index` with `username`/
  `password` fields — if the school changes their login page (adds a
  CSRF token, captcha, etc.) this script will need updating to match.
- PDF attachments are fetched by following each attachment's viewer page
  and extracting the real file URL from an embedded `file_path` JS
  variable, then downloading that URL directly.
