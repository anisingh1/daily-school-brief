from datetime import datetime, timedelta

import pytest


def _msg(offset_hours, msg_id):
    posted = datetime.now() - timedelta(hours=offset_hours)
    return {
        "id": msg_id,
        "title": "t",
        "posted_at": posted.isoformat(),
        "body": "b",
        "attachments": [],
    }


def test_filter_recent_includes_message_within_window():
    from scrape_udt import filter_recent

    messages = [_msg(1, "recent")]
    result = filter_recent(messages, lookback_hours=36)
    assert len(result) == 1


def test_filter_recent_excludes_message_before_cutoff():
    from scrape_udt import filter_recent

    messages = [_msg(40, "old")]
    result = filter_recent(messages, lookback_hours=36)
    assert result == []


def test_filter_recent_sorts_most_recent_first():
    from scrape_udt import filter_recent

    messages = [_msg(30, "a"), _msg(2, "b"), _msg(10, "c")]
    result = filter_recent(messages, lookback_hours=36)
    assert [m["id"] for m in result] == ["b", "c", "a"]


def test_login_raises_on_failed_login():
    from scrape_udt import login

    class FakeResponse:
        text = '<div id="login-form"></div>'

        def raise_for_status(self):
            pass

    class FakeSession:
        def post(self, *args, **kwargs):
            return FakeResponse()

    with pytest.raises(RuntimeError):
        login(FakeSession())


class _FakeSession:
    def __init__(self):
        self.headers = {}


class _FakeRequests:
    """Stand-in for the `requests` module, patched onto scrape_udt so
    fetch_recent_messages() gets our fake session instead of a real one."""

    def __init__(self, session):
        self._session = session

    def Session(self):
        return self._session


def test_fetch_recent_messages_raises_on_login_failure(monkeypatch):
    import scrape_udt

    fake_session = _FakeSession()
    monkeypatch.setattr(scrape_udt, "requests", _FakeRequests(fake_session))

    def fake_login(session):
        raise RuntimeError("login failed")

    monkeypatch.setattr(scrape_udt, "login", fake_login)

    with pytest.raises(RuntimeError):
        scrape_udt.fetch_recent_messages(lookback_hours=36)


def test_fetch_recent_messages_returns_filtered_without_downloading_by_default(monkeypatch):
    import scrape_udt

    fake_session = _FakeSession()
    monkeypatch.setattr(scrape_udt, "requests", _FakeRequests(fake_session))
    monkeypatch.setattr(scrape_udt, "login", lambda session: None)
    monkeypatch.setattr(
        scrape_udt,
        "fetch_activity_messages",
        lambda session: [_msg(1, "recent"), _msg(40, "old")],
    )

    download_calls = []
    monkeypatch.setattr(
        scrape_udt,
        "download_message_attachments",
        lambda session, messages: download_calls.append(messages),
    )

    result = scrape_udt.fetch_recent_messages(lookback_hours=36)

    assert [m["id"] for m in result] == ["recent"]
    assert download_calls == []


def test_fetch_recent_messages_downloads_attachments_when_requested(monkeypatch):
    import scrape_udt

    fake_session = _FakeSession()
    monkeypatch.setattr(scrape_udt, "requests", _FakeRequests(fake_session))
    monkeypatch.setattr(scrape_udt, "login", lambda session: None)
    monkeypatch.setattr(
        scrape_udt,
        "fetch_activity_messages",
        lambda session: [_msg(1, "recent")],
    )

    download_calls = []
    monkeypatch.setattr(
        scrape_udt,
        "download_message_attachments",
        lambda session, messages: download_calls.append((session, messages)),
    )

    result = scrape_udt.fetch_recent_messages(lookback_hours=36, download_attachments=True)

    assert len(download_calls) == 1
    called_session, called_messages = download_calls[0]
    assert called_session is fake_session
    assert called_messages == result
