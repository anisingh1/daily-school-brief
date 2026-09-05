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

  **Caveat - unescaped quotes/newlines:** `%notification_text%` is a
  naive string paste into the JSON template. A message containing a
  `"` or a line break will produce a malformed JSON line, which
  `fetch_whatsapp.py`'s parser silently skips - that message is
  silently lost. Check whether your MacroDroid tier's "Local
  Variables" / "Magic Text" reference offers a JSON-encode/escape
  action (or a JavaScript/scripting action that can JSON-encode a
  variable) and apply it to `%notification_text%` (and, less
  critically, `%notification_title%`) before writing the line. If no
  such function is available in your tier, periodically spot-check the
  Drive log file against the actual group history so you notice if
  messages are being silently dropped.

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
