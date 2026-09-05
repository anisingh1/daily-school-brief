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
