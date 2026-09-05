import json
from datetime import datetime

import portal_archive


def test_read_last_run_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_archive, "LAST_RUN_PATH", tmp_path / "last_run.json")
    assert portal_archive.read_last_run() is None


def test_save_and_read_last_run_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_archive, "DATA_DIR", tmp_path)
    monkeypatch.setattr(portal_archive, "LAST_RUN_PATH", tmp_path / "last_run.json")

    portal_archive.save_last_run(datetime(2026, 9, 5, 18, 0, 0))

    assert portal_archive.read_last_run() == datetime(2026, 9, 5, 18, 0, 0)


def test_compute_portal_cutoff_uses_last_run_when_present(monkeypatch):
    saved = datetime(2026, 9, 4, 19, 30)
    monkeypatch.setattr(portal_archive, "read_last_run", lambda: saved)
    assert portal_archive.compute_portal_cutoff() == saved


def test_compute_portal_cutoff_falls_back_to_month_anchor_when_absent(monkeypatch):
    monkeypatch.setattr(portal_archive, "read_last_run", lambda: None)
    from cutoff import month_anchor
    assert portal_archive.compute_portal_cutoff() == month_anchor()


def test_load_archive_returns_empty_list_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_archive, "ARCHIVE_PATH", tmp_path / "portal_messages.json")
    assert portal_archive.load_archive() == []


def test_merge_into_archive_dedupes_by_id(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_archive, "ARCHIVE_PATH", tmp_path / "portal_messages.json")
    existing = [
        {"id": "1", "title": "old version", "posted_at": "2026-09-01T10:00:00", "body": "b", "attachments": []},
    ]
    (tmp_path / "portal_messages.json").write_text(json.dumps(existing))

    new_messages = [
        {"id": "1", "title": "updated version", "posted_at": "2026-09-01T10:00:00", "body": "b", "attachments": []},
        {"id": "2", "title": "new message", "posted_at": "2026-09-05T10:00:00", "body": "b2", "attachments": []},
    ]

    merged = portal_archive.merge_into_archive(new_messages)

    assert len(merged) == 2
    ids = {m["id"] for m in merged}
    assert ids == {"1", "2"}
    updated = next(m for m in merged if m["id"] == "1")
    assert updated["title"] == "updated version"


def test_merge_into_archive_sorts_most_recent_first(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_archive, "ARCHIVE_PATH", tmp_path / "portal_messages.json")
    new_messages = [
        {"id": "a", "title": "t", "posted_at": "2026-09-01T10:00:00", "body": "b", "attachments": []},
        {"id": "b", "title": "t", "posted_at": "2026-09-05T10:00:00", "body": "b", "attachments": []},
    ]
    merged = portal_archive.merge_into_archive(new_messages)
    assert [m["id"] for m in merged] == ["b", "a"]


def test_merge_into_archive_does_not_collapse_messages_with_empty_id(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(portal_archive, "ARCHIVE_PATH", tmp_path / "portal_messages.json")
    new_messages = [
        {"id": "", "title": "no id one", "posted_at": "2026-09-01T10:00:00", "body": "b", "attachments": []},
        {"id": "", "title": "no id two", "posted_at": "2026-09-05T10:00:00", "body": "b2", "attachments": []},
    ]

    merged = portal_archive.merge_into_archive(new_messages)

    assert len(merged) == 2
    titles = {m["title"] for m in merged}
    assert titles == {"no id one", "no id two"}


def test_save_archive_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_archive, "DATA_DIR", tmp_path)
    monkeypatch.setattr(portal_archive, "ARCHIVE_PATH", tmp_path / "portal_messages.json")
    messages = [{"id": "1", "title": "t", "posted_at": "2026-09-05T10:00:00", "body": "b", "attachments": []}]

    portal_archive.save_archive(messages)

    assert json.loads((tmp_path / "portal_messages.json").read_text()) == messages
