import json

import daily_brief


def test_gather_captures_portal_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(daily_brief, "compute_portal_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["error"] == "RuntimeError: login failed"
    assert result["portal"]["messages"] == []
    assert result["whatsapp"]["error"] is None


def test_gather_merges_and_saves_archive_on_portal_success(monkeypatch):
    saved = {}
    monkeypatch.setattr(daily_brief, "compute_portal_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [{"id": "new", "title": "x"}])
    monkeypatch.setattr(
        daily_brief,
        "merge_into_archive",
        lambda new: [{"id": "new", "title": "x"}, {"id": "old", "title": "y"}],
    )
    monkeypatch.setattr(daily_brief, "save_archive", lambda archive: saved.setdefault("archive", archive))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: saved.setdefault("last_run", dt))
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["messages"] == [{"id": "new", "title": "x"}, {"id": "old", "title": "y"}]
    assert saved["archive"] == [{"id": "new", "title": "x"}, {"id": "old", "title": "y"}]
    assert "last_run" in saved


def test_gather_does_not_save_archive_or_cursor_on_portal_failure(monkeypatch):
    saved = {}

    def failing_fetch(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(daily_brief, "compute_portal_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "save_archive", lambda archive: saved.setdefault("archive", archive))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: saved.setdefault("last_run", dt))
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    daily_brief.gather()

    assert "archive" not in saved
    assert "last_run" not in saved


def test_gather_does_not_advance_cursor_if_archive_save_fails(monkeypatch):
    saved = {}

    def failing_save_archive(archive):
        raise RuntimeError("disk full")

    monkeypatch.setattr(daily_brief, "compute_portal_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [{"id": "new", "title": "x"}])
    monkeypatch.setattr(daily_brief, "merge_into_archive", lambda new: [{"id": "new", "title": "x"}])
    monkeypatch.setattr(daily_brief, "save_archive", failing_save_archive)
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: saved.setdefault("last_run", dt))
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert "last_run" not in saved
    assert result["portal"]["error"] == "RuntimeError: disk full"


def test_gather_captures_whatsapp_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("drive unreachable")

    monkeypatch.setattr(daily_brief, "compute_portal_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "merge_into_archive", lambda new: [])
    monkeypatch.setattr(daily_brief, "save_archive", lambda archive: None)
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", failing_fetch)

    result = daily_brief.gather()

    assert result["whatsapp"]["error"] == "RuntimeError: drive unreachable"
    assert result["portal"]["error"] is None


def test_gather_uses_month_anchor_for_whatsapp_cutoff(monkeypatch):
    from cutoff import month_anchor as real_month_anchor

    calls = {}

    def fake_whatsapp_fetch(**kwargs):
        calls.update(kwargs)
        return []

    monkeypatch.setattr(daily_brief, "compute_portal_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "merge_into_archive", lambda new: [])
    monkeypatch.setattr(daily_brief, "save_archive", lambda archive: None)
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", fake_whatsapp_fetch)

    daily_brief.gather()

    assert calls["cutoff"] == real_month_anchor()


def test_gather_uses_portal_cutoff_and_downloads_attachments(monkeypatch):
    calls = {}

    def fake_fetch(**kwargs):
        calls.update(kwargs)
        return []

    monkeypatch.setattr(daily_brief, "compute_portal_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", fake_fetch)
    monkeypatch.setattr(daily_brief, "merge_into_archive", lambda new: [])
    monkeypatch.setattr(daily_brief, "save_archive", lambda archive: None)
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    daily_brief.gather()

    assert calls["cutoff"] == "fixed-cutoff"
    assert calls["download_attachments"] is True


def test_run_writes_output_file(monkeypatch, tmp_path):
    fixed_result = {
        "portal": {"messages": [], "error": None},
        "whatsapp": {"messages": [], "error": None},
    }
    monkeypatch.setattr(daily_brief, "gather", lambda: fixed_result)
    out_path = tmp_path / "out.json"
    monkeypatch.setattr(daily_brief, "OUTPUT_PATH", out_path)

    result = daily_brief.run()

    assert out_path.exists()
    assert json.loads(out_path.read_text()) == result == fixed_result
