import json

import daily_brief


def test_gather_captures_portal_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["error"] == "RuntimeError: login failed"
    assert result["portal"]["messages"] == []
    assert result["whatsapp"]["error"] is None
    assert result["whatsapp"]["messages"] == []


def test_gather_returns_messages_on_success(monkeypatch):
    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
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

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", failing_fetch)

    result = daily_brief.gather()

    assert result["whatsapp"]["error"] == "RuntimeError: drive unreachable"
    assert result["portal"]["error"] is None


def test_gather_downloads_portal_attachments_with_shared_cutoff(monkeypatch):
    portal_calls = {}
    whatsapp_calls = {}

    def fake_fetch(**kwargs):
        portal_calls.update(kwargs)
        return []

    def fake_whatsapp_fetch(**kwargs):
        whatsapp_calls.update(kwargs)
        return []

    monkeypatch.setattr(daily_brief, "compute_cutoff", lambda: "fixed-cutoff")
    monkeypatch.setattr(daily_brief, "fetch_recent_messages", fake_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", fake_whatsapp_fetch)

    daily_brief.gather()

    assert portal_calls["download_attachments"] is True
    assert portal_calls["cutoff"] == "fixed-cutoff"
    assert whatsapp_calls["cutoff"] == "fixed-cutoff"


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
