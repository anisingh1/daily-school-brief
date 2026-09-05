import daily_brief


def test_gather_captures_portal_error(monkeypatch):
    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(daily_brief, "fetch_recent_messages", failing_fetch)
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", lambda **kwargs: [])

    result = daily_brief.gather()

    assert result["portal"]["error"] == "login failed"
    assert result["portal"]["messages"] == []
    assert result["whatsapp"]["error"] is None
    assert result["whatsapp"]["messages"] == []


def test_gather_returns_messages_on_success(monkeypatch):
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

    monkeypatch.setattr(daily_brief, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(daily_brief, "fetch_recent_whatsapp_messages", failing_fetch)

    result = daily_brief.gather()

    assert result["whatsapp"]["error"] == "drive unreachable"
    assert result["portal"]["error"] is None
