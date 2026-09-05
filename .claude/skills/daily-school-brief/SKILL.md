---
name: daily-school-brief
description: Generate the daily school brief (homework, tomorrow's agenda, dress code, other reminders) from the school portal and WhatsApp group logs, and push a notification with it. Use when asked to run or generate the daily school brief, or on the scheduled evening trigger.
---

# Daily School Brief

## What this does

Combines two message sources - the school web portal (with a permanent,
git-committed archive of every message ever scraped) and the school
WhatsApp group (captured via phone automation into a Google Drive file,
covering a couple days before the start of the current calendar month
onward) - and produces a short brief covering:

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
   (a string or null). The portal's `messages` list is the FULL
   accumulated archive (every message ever scraped), not just what's
   new this run. Portal messages may include an `attachments` list; a
   downloaded attachment has a `saved_as` local file path.

   If `python daily_brief.py` fails to run (crashes, `python` not
   found, etc.) or `output/daily_brief_input.json` does not exist
   afterward, don't stop silently - send a push notification saying
   the daily brief couldn't be generated, including a short reason if
   one is available, and stop there.

2. Commit and push any changes under `data/` (the portal message
   archive, cursor, and downloaded PDFs) so they persist for the next
   run:

   ```bash
   git add data/
   git diff --cached --quiet || git commit -m "Update portal archive"
   git push
   ```

   This is necessary because a scheduled cloud routine clones this repo
   fresh on every run - anything written to `data/` during this run is
   lost unless it's committed and pushed back before the run ends. If
   this step fails for any reason - no push access, or a rejected
   non-fast-forward push because another run or a human pushed in
   between - just note it as a warning in the brief and continue. Do
   NOT force-push, rebase, or otherwise try to resolve a rejected push;
   a failure here doesn't affect today's brief, only whether tomorrow's
   run starts from today's updated archive, and it's safe to just let
   the next run retry from wherever the remote actually is.

3. Read `output/daily_brief_input.json` (path relative to the project
   root from step 1 - this only works if you're actually in that
   directory when you run step 1).

4. For each portal message that has an attachment with a `saved_as`
   path, `Read` that file directly (Claude Code's `Read` tool handles
   PDFs natively). Homework, agenda, and dress-code details are often
   inside the document itself - a monthly planner PDF, for instance -
   rather than in the message body text, so don't rely on the body
   text alone when an attachment is present.

5. For each source with a non-null `error`, note it as a warning to
   include at the top of the brief (e.g. "couldn't reach school
   portal") - a failure in one source should not stop you from using
   the other source's messages.

6. If both sources have zero messages and no errors, the brief is just:
   "Nothing new from the school portal or WhatsApp group."

7. Otherwise, read through all messages (and any attachment content
   read in step 4) from both sources and use your own judgment to
   extract (the content is unstructured free text - don't pattern-match
   on fixed keywords):
   - **Homework**: any assignment, reading, or task mentioned for the
     child to do.
   - **Tomorrow's agenda**: events, special activities, holidays, timing
     changes, or notices that apply to tomorrow specifically (use
     today's date in IST - India Standard Time, UTC+5:30, the school's
     timezone - to work out what "tomorrow" refers to; do not use the
     local timezone of the machine or sandbox running this skill).
     Content posted at any point in the past (e.g. a monthly planner
     from weeks ago) that happens to apply to tomorrow counts just as
     much as something posted today - the portal archive is complete,
     so don't assume only recent messages matter.
   - **Dress code**: any uniform/dress instructions that apply tomorrow
     (e.g. "sports day, wear house colors", "PE kit tomorrow").
   - **Other reminders**: anything else worth a parent's attention (fee
     due dates, forms to sign, items to bring) that doesn't fit the
     above.
   Omit a section entirely if there's nothing for it, rather than
   forcing an empty slot.

8. Compose the brief as plain text with short section headers. This is
   a draft/internal step - it's fine for this draft to span multiple
   lines and sections.

9. Condense that draft into the actual notification message: the
   PushNotification tool requires a single line of plain text with no
   markdown formatting. Send it with `status: "proactive"`, `message`
   = the condensed brief. Mobile OSes truncate long notifications, so
   keep the single line under ~200 characters where possible - lead
   with the most time-sensitive items (tomorrow's dress code, homework
   due tomorrow) first, since anything after that point may get cut
   off if the full brief would run longer.
