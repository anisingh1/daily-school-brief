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
