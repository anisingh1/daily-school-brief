import json
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

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
    assert portal_archive.compute_portal_cutoff() == month_anchor(months_back=3)


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


def test_is_within_retention_keeps_recent_message():
    now = datetime(2026, 9, 5)
    recent = (now - timedelta(days=10)).isoformat()
    assert portal_archive.is_within_retention(recent, now) is True


def test_is_within_retention_drops_message_older_than_three_months():
    now = datetime(2026, 9, 5)
    old = (now - relativedelta(months=4)).isoformat()
    assert portal_archive.is_within_retention(old, now) is False


def test_prune_archive_keeps_recent_and_drops_old():
    now = datetime(2026, 9, 5)
    recent = {
        "id": "1", "title": "t",
        "posted_at": (now - timedelta(days=5)).isoformat(),
        "body": "b", "attachments": [],
    }
    old = {
        "id": "2", "title": "t",
        "posted_at": (now - relativedelta(months=4)).isoformat(),
        "body": "b", "attachments": [],
    }

    result = portal_archive.prune_archive([recent, old], now)

    assert result == [recent]


def test_prune_archive_deletes_orphaned_pdf(tmp_path):
    now = datetime(2026, 9, 5)
    pdf_path = tmp_path / "2_Homework.pdf"
    pdf_path.write_bytes(b"pdf content")

    old = {
        "id": "2", "title": "t",
        "posted_at": (now - relativedelta(months=4)).isoformat(),
        "body": "b",
        "attachments": [{"name": "Homework", "href": "x", "saved_as": str(pdf_path)}],
    }

    portal_archive.prune_archive([old], now)

    assert not pdf_path.exists()


def test_prune_archive_keeps_pdf_for_recent_message(tmp_path):
    now = datetime(2026, 9, 5)
    pdf_path = tmp_path / "1_Homework.pdf"
    pdf_path.write_bytes(b"pdf content")

    recent = {
        "id": "1", "title": "t",
        "posted_at": (now - timedelta(days=5)).isoformat(),
        "body": "b",
        "attachments": [{"name": "Homework", "href": "x", "saved_as": str(pdf_path)}],
    }

    portal_archive.prune_archive([recent], now)

    assert pdf_path.exists()


def test_prune_archive_handles_empty_id_messages_with_distinct_attachment_paths(tmp_path):
    # Regression test for the scrape_udt.py filename-collision bug: two messages
    # both lacking an "id" (the parser's fallback for an HTML element with no id
    # attribute) used to compute the same saved_as filename if they also shared
    # an attachment display name, so pruning one would delete the other's file
    # too. Post-fix, their saved_as paths are distinct (derived from the
    # attachment's href instead of the empty id) - this asserts prune_archive
    # only touches the pruned message's own file.
    now = datetime(2026, 9, 5)
    old_pdf_path = tmp_path / "_viewer1_Homework.pdf"
    old_pdf_path.write_bytes(b"old pdf content")
    recent_pdf_path = tmp_path / "_viewer2_Homework.pdf"
    recent_pdf_path.write_bytes(b"recent pdf content")

    old = {
        "id": "", "title": "t",
        "posted_at": (now - relativedelta(months=4)).isoformat(),
        "body": "b",
        "attachments": [{"name": "Homework", "href": "/viewer1", "saved_as": str(old_pdf_path)}],
    }
    recent = {
        "id": "", "title": "t",
        "posted_at": (now - timedelta(days=5)).isoformat(),
        "body": "b",
        "attachments": [{"name": "Homework", "href": "/viewer2", "saved_as": str(recent_pdf_path)}],
    }

    result = portal_archive.prune_archive([old, recent], now)

    assert result == [recent]
    assert not old_pdf_path.exists()
    assert recent_pdf_path.exists()
