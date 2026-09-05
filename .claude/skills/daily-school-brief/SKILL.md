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

   The project root is the directory containing `daily_brief.py`,
   `scrape_udt.py`, and `fetch_whatsapp.py`. If you're not already
   there (e.g. in a fresh clone on a scheduled cloud routine), `cd`
   into it first before running the command.

   This writes `output/daily_brief_input.json` with two sections,
   `portal` and `whatsapp`, each having `messages` (a list) and `error`
   (a string or null).

   If `python daily_brief.py` fails to run (crashes, `python` not
   found, etc.) or `output/daily_brief_input.json` does not exist
   afterward, don't stop silently - send a push notification saying
   the daily brief couldn't be generated, including a short reason if
   one is available, and stop there.

2. Read `output/daily_brief_input.json` (path relative to the project
   root from step 1 - this only works if you're actually in that
   directory when you run step 1).

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
     today's date in IST - India Standard Time, UTC+5:30, the school's
     timezone - to work out what "tomorrow" refers to; do not use the
     local timezone of the machine or sandbox running this skill).
   - **Dress code**: any uniform/dress instructions that apply tomorrow
     (e.g. "sports day, wear house colors", "PE kit tomorrow").
   - **Other reminders**: anything else worth a parent's attention (fee
     due dates, forms to sign, items to bring) that doesn't fit the
     above.
   Omit a section entirely if there's nothing for it, rather than
   forcing an empty slot.

6. Compose the brief as plain text with short section headers. This is
   a draft/internal step - it's fine for this draft to span multiple
   lines and sections.

7. Condense that draft into the actual notification message: the
   PushNotification tool requires a single line of plain text with no
   markdown formatting. Send it with `status: "proactive"`, `message`
   = the condensed brief. Mobile OSes truncate long notifications, so
   keep the single line under ~200 characters where possible - lead
   with the most time-sensitive items (tomorrow's dress code, homework
   due tomorrow) first, since anything after that point may get cut
   off if the full brief would run longer.
