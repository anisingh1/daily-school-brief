# Daily School Brief — Always-On Service — Design

## Goal

Move off the current model (a Claude Code skill triggered once daily by a
scheduled cloud routine, emailing an HTML brief) to an always-on service
running on the user's own Raspberry Pi / home server, which:

- Polls the WhatsApp source every 10 minutes and the school portal every 60
  minutes, regenerating the brief only when something new is found.
- Also forces one regeneration per day (~7:30pm IST, matching today's
  schedule) as a backstop, so date-relative fields (tomorrow's dress code,
  which day's classwork carries forward) stay correct even across a gap
  with no new messages (e.g. a weekend).
- Serves the current brief on a simple web page on the home LAN, instead
  of sending it by email.

This supersedes the architecture in
`docs/superpowers/specs/2026-09-05-daily-school-brief-design.md` (scheduled
cloud agent + email delivery). That design's fetcher logic (`scrape_udt.py`,
`fetch_whatsapp.py`, `cutoff.py`, the portal archive/cursor) is reused as-is
where possible; what changes is *when* things run, *how* the brief is
generated, and *how* it's delivered.

## Why not X

- **Cloud-scheduled agent run every 10 min**: rejected. Cloud routines are
  designed for periodic scheduled runs, not tight polling, and each run
  would cost an LLM invocation whether or not anything new existed. A
  persistent process that only calls the LLM when there's new content (or
  once/day as a backstop) is both cheaper and a better fit for "check
  every 10 min."
- **Managed cloud VM/container (Fly.io, Railway, etc.)**: not needed — the
  user already has a Raspberry Pi / home server running 24/7.
- **Polling the school portal every 10 min (same cadence as WhatsApp)**:
  rejected. ~144 logins/day vs. today's ~1/day meaningfully raises the risk
  of the portal treating this as abuse or the account getting rate-limited/
  locked. WhatsApp polling (IMAP against the user's own Gmail) doesn't carry
  that risk, so it keeps the tighter 10-minute cadence while the portal
  polls hourly instead.
- **Public/internet-exposed web page**: rejected — only needs to be viewed
  from home Wi-Fi, so there's no need for a reverse proxy, dynamic DNS,
  tunnel, or authentication. LAN-only keeps this simple.
- **git-committed archive as the persistence mechanism**: this existed
  specifically because the old scheduled cloud agent cloned the repo fresh
  on every run — anything not pushed back to GitHub before the run ended
  was lost. A persistent Pi process doesn't have that problem; its local
  disk *is* the persistence layer, so the git-commit-and-push step
  (`commit_archive.py`) is removed from the runtime path.

## Architecture

```
[School Portal]                          [Gmail inbox]
      │                                        │
      │ scrape_udt.py, login,                  │ fetch_whatsapp.py,
      │ portal_archive cursor                  │ IMAP cursor
      │ polled every 60 min                    │ polled every 10 min
      │                                        │
      └───────────────┬────────────────────────┘
                       ▼
         ┌───────────────────────────────────┐
         │   service.py (systemd, always on)  │
         │                                     │
         │  scheduler:                         │
         │   - whatsapp loop (10 min)          │
         │   - portal loop (60 min)            │
         │   - daily backstop (~7:30pm IST)     │
         │        │ (new content found, or      │
         │        │  backstop fires)             │
         │        ▼                              │
         │   regenerate_brief() [locked]         │
         │     → generate_brief.py               │
         │       (Anthropic API call, same       │
         │        categorization rules as        │
         │        today's SKILL.md + any new     │
         │        PDFs as document blocks)       │
         │     → writes output/daily_brief_      │
         │       content.json + rendered HTML    │
         │                                        │
         │  web server (Flask):                   │
         │     serves latest rendered brief at    │
         │     http://<pi-hostname>.local:8765/   │
         └───────────────────────────────────────┘
                       ▲
                       │ LAN only, no auth
                  [Browser at home]
```

## Components

### 1. Portal fetcher — `scrape_udt.py`, `portal_archive.py` (reused as-is)

No logic changes. Still logs in, scrapes, dedups by message id into
`data/portal_messages.json`, and tracks a cursor in `data/last_run.json`.
Now invoked once per 60-minute poll instead of once per day. The 2-month
pruning behavior is unchanged.

### 2. WhatsApp fetcher — `fetch_whatsapp.py` (gains a persisted cursor)

Currently always re-scans from `cutoff.month_anchor()` on every run, which
was fine at once-a-day cadence but would mean re-fetching/re-filtering the
whole month's IMAP mailbox every 10 minutes. Adds a persisted cursor,
`data/whatsapp_last_run.json` (`{"last_run": "<isoformat>"}`), mirroring
the portal's pattern:

- First run (no cursor file yet): fall back to `cutoff.month_anchor()`,
  same as today.
- Subsequent runs: fetch only messages since the cursor, advance it after
  a successful fetch.

### 3. `service.py` (new) — the always-on entrypoint

Starts three scheduled loops (WhatsApp/10 min, portal/60 min, daily
backstop/~7:30pm IST) and the web server, all in one process. Holds a
lock around brief regeneration so two triggers (e.g. a WhatsApp poll and
the daily backstop) firing close together can't race. Scheduling is a
plain background loop per task (a thread per interval, each sleeping until
its next run time) — no extra scheduling dependency needed for three fixed
intervals, and it matches the rest of the codebase's plain-synchronous
style (no existing script uses `asyncio` or a scheduling library).

### 4. `generate_brief.py` (new) — replaces the Claude Code skill

Calls the Anthropic API directly (Python SDK, `ANTHROPIC_API_KEY` from
`.env`) with the same categorization instructions currently embedded in
`.claude/skills/daily-school-brief/SKILL.md` steps 4–8 (Aviraj callouts,
per-student roster checks, carry-forward classwork/homework, fixed
swim/skate schedule with override rule, 5-day reminder window), built from
the same input envelope `daily_brief.py` assembles today. Portal/WhatsApp
PDF attachments are sent as document content blocks in the API call
(replacing the skill's `Read`-the-PDF-directly step). Returns the same
JSON shape as today: `date`, `warnings`, `aviraj_highlight`, `classwork`,
`homework`, `agenda`, `dress_code`, `reminders`.

### 5. `render_email.py` → renamed `render_brief.py` (repurposed)

Same rendering logic, reused to produce the HTML shown on the web page
instead of an email body. Email-specific concerns (if any) are dropped.

### 6. Web page (new, Flask)

Single route, `/`, rendering the latest `output/daily_brief_content.json`
via `render_brief.py`. Flask (run via its own built-in server, threaded)
is used rather than an async framework, to match the rest of the
codebase's plain-synchronous style and because a single-route, single-user,
LAN-only page has no need for async concurrency. Reachable at
`http://<pi-hostname>.local:8765/` on the home LAN (port configurable via
`.env`'s new `PORT`, default `8765`). No authentication, no external
exposure. If the last
regeneration attempt failed, the last successfully-generated brief is
still shown, with a small note (e.g. "last updated <time>; last attempt at
<time> failed: <reason>") rather than showing nothing.

### 7. Removed

- `send_email.py` and SMTP config (`SMTP_USERNAME`, `SMTP_APP_PASSWORD`,
  `EMAIL_TO` in `.env`) — delivery is the web page now, not email.
- `commit_archive.py` and the git-commit-and-push step — no longer needed
  since the Pi's local disk persists across runs (the process never
  restarts from a fresh clone the way the old cloud routine did).
- The scheduled cloud routine itself (the `schedule`-skill-based trigger)
  and the `.claude/skills/daily-school-brief/SKILL.md` skill — superseded
  by `service.py` + `generate_brief.py`. `daily_brief.py`'s envelope-
  building logic is kept but now called from `generate_brief.py` instead
  of being a separate skill step.

### 8. New `.env` values

- `ANTHROPIC_API_KEY` — for direct API calls from `generate_brief.py`.
- `PORT` — port for the Flask web page, default `8765`.
- Existing `UDT_USERNAME`, `UDT_PASSWORD`, IMAP/Gmail credentials are kept
  unchanged.

### 9. Deployment

A systemd unit (e.g. `daily-school-brief.service`) runs `service.py` on
boot and restarts it on failure, so the service survives Pi reboots
without manual intervention.

## Data flow / trigger logic

- **WhatsApp loop (10 min)**: fetch new messages since the IMAP cursor →
  if any found, merge/save, advance cursor, trigger `regenerate_brief()`.
  If none found, no-op (no LLM call).
- **Portal loop (60 min)**: fetch since the portal cursor → if the merge
  into the archive adds anything new, trigger `regenerate_brief()`.
- **Daily backstop (~7:30pm IST, once/day)**: always triggers
  `regenerate_brief()`, regardless of whether anything new arrived, so
  "tomorrow"-relative fields stay correct across gaps in new messages.
- **`regenerate_brief()`**: acquires the lock, builds the input envelope,
  calls the Anthropic API, writes `output/daily_brief_content.json` and
  the rendered HTML, releases the lock.

## Error handling

- Best-effort per source, same as today: a portal or WhatsApp fetch
  failure surfaces as a warning in the next generated brief rather than
  blocking the other source.
- If `regenerate_brief()`'s LLM call itself fails, the web page keeps
  showing the last successfully-generated brief, with a note about the
  last failed attempt and its reason, rather than going blank or crashing
  the service.
- No retries or alerting beyond this — personal tool, not a monitored
  service, consistent with the existing design's scope.

## Testing approach

- Unit tests for the new WhatsApp IMAP cursor logic and for
  `generate_brief.py`'s input-envelope/prompt construction, mocking the
  Anthropic API call — following the existing patterns in `tests/`.
- Manual verification on the actual Pi: systemd service starts on boot,
  survives a reboot, and the web page is reachable from another device on
  the home LAN.
- One live end-to-end dry run (real portal login, real IMAP fetch, real
  Anthropic API call) before leaving the service running unattended,
  checked by hand against expected output.
- No load/scale testing — single-user, LAN-only, personal tool.

## Scope / out of scope

- Single child, single class WhatsApp group, single portal account —
  unchanged from the existing design.
- LAN-only web access — no external exposure, no authentication, no
  multi-user support.
- No brief history/archive page — the web page shows only the current/
  latest brief, matching how the tool is used today (one brief at a time).
- No database — local JSON files on the Pi's disk, same shapes as today
  (`data/portal_messages.json`, `data/last_run.json`,
  `data/whatsapp_last_run.json`, `output/daily_brief_content.json`).
