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
