import json
from datetime import datetime

import daily_brief


def test_gather_captures_portal_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["error"] == "RuntimeError: login failed"
    assert result["portal"]["messages"] == []
    assert result["whatsapp"]["error"] is None
    assert result["whatsapp"]["messages"] == []


def test_gather_returns_messages_on_success(monkeypatch):
    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [{"title": "x"}])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [{"text": "y"}])

    result = daily_brief.gather()

    assert result["portal"]["messages"] == [{"title": "x"}]
    assert result["portal"]["error"] is None
    assert result["whatsapp"]["messages"] == [{"text": "y"}]
    assert result["whatsapp"]["error"] is None


def test_gather_captures_whatsapp_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("drive unreachable")

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: None)
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", failing_fetch)

    result = daily_brief.gather()

    assert result["whatsapp"]["error"] == "RuntimeError: drive unreachable"
    assert result["portal"]["error"] is None


def test_gather_saves_cursor_only_when_both_sources_succeed(monkeypatch):
    saved = {}
    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: saved.setdefault("called_with", dt))
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    daily_brief.gather()

    assert "called_with" in saved


def test_gather_does_not_save_cursor_when_a_source_fails(monkeypatch):
    saved = {}

    def failing_fetch(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: datetime(2026, 9, 4))
    monkeypatch.setattr(daily_brief, "save_last_run", lambda dt: saved.setdefault("called_with", dt))
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    daily_brief.gather()

    assert "called_with" not in saved


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
