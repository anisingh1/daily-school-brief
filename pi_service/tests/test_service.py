import pi_service.service as service


def test_portal_poller_reports_changed_when_new_messages_found(monkeypatch):
    poller = service.PortalPoller()
    monkeypatch.setattr(service.portal_archive, "compute_portal_cutoff", lambda: "cutoff")
    monkeypatch.setattr(service.scrape_udt, "fetch_recent_messages", lambda **kwargs: [{"id": "1"}])
    monkeypatch.setattr(service.portal_archive, "merge_into_archive", lambda new: [{"id": "1"}])
    monkeypatch.setattr(service.portal_archive, "prune_archive", lambda archive: archive)
    monkeypatch.setattr(service.portal_archive, "save_archive", lambda archive: None)
    monkeypatch.setattr(service.portal_archive, "save_last_run", lambda dt: None)

    assert poller.tick() is True
    assert poller.last_error is None


def test_portal_poller_reports_unchanged_when_no_new_messages(monkeypatch):
    poller = service.PortalPoller()
    monkeypatch.setattr(service.portal_archive, "compute_portal_cutoff", lambda: "cutoff")
    monkeypatch.setattr(service.scrape_udt, "fetch_recent_messages", lambda **kwargs: [])
    monkeypatch.setattr(service.portal_archive, "merge_into_archive", lambda new: [])
    monkeypatch.setattr(service.portal_archive, "prune_archive", lambda archive: archive)
    monkeypatch.setattr(service.portal_archive, "save_archive", lambda archive: None)
    monkeypatch.setattr(service.portal_archive, "save_last_run", lambda dt: None)

    assert poller.tick() is False


def test_portal_poller_records_error_and_does_not_raise(monkeypatch):
    poller = service.PortalPoller()
    monkeypatch.setattr(service.portal_archive, "compute_portal_cutoff", lambda: "cutoff")

    def failing_fetch(**kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(service.scrape_udt, "fetch_recent_messages", failing_fetch)

    assert poller.tick() is False
    assert poller.last_error == "RuntimeError: login failed"


def test_whatsapp_poller_first_tick_never_reports_changed(monkeypatch):
    poller = service.WhatsAppPoller()
    monkeypatch.setattr(service.fetch_whatsapp, "fetch_recent_whatsapp_messages", lambda **kwargs: [{"sender": "A"}])

    assert poller.tick() is False
    assert poller.last_messages == [{"sender": "A"}]


def test_whatsapp_poller_reports_changed_when_messages_differ(monkeypatch):
    poller = service.WhatsAppPoller()
    responses = iter([[{"sender": "A"}], [{"sender": "A"}, {"sender": "B"}]])
    monkeypatch.setattr(service.fetch_whatsapp, "fetch_recent_whatsapp_messages", lambda **kwargs: next(responses))

    assert poller.tick() is False
    assert poller.tick() is True


def test_whatsapp_poller_reports_unchanged_when_messages_are_the_same(monkeypatch):
    poller = service.WhatsAppPoller()
    monkeypatch.setattr(service.fetch_whatsapp, "fetch_recent_whatsapp_messages", lambda **kwargs: [{"sender": "A"}])

    poller.tick()
    assert poller.tick() is False


def test_whatsapp_poller_records_error_and_keeps_last_good_messages(monkeypatch):
    poller = service.WhatsAppPoller()
    monkeypatch.setattr(service.fetch_whatsapp, "fetch_recent_whatsapp_messages", lambda **kwargs: [{"sender": "A"}])
    poller.tick()

    def failing_fetch(**kwargs):
        raise RuntimeError("imap down")

    monkeypatch.setattr(service.fetch_whatsapp, "fetch_recent_whatsapp_messages", failing_fetch)

    assert poller.tick() is False
    assert poller.last_error == "RuntimeError: imap down"
    assert poller.last_messages == [{"sender": "A"}]


import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def test_next_daily_backstop_returns_today_when_before_time():
    now = datetime(2026, 9, 7, 10, 0, tzinfo=IST)
    assert service.next_daily_backstop(now) == datetime(2026, 9, 7, 19, 30, tzinfo=IST)


def test_next_daily_backstop_returns_tomorrow_when_after_time():
    now = datetime(2026, 9, 7, 20, 0, tzinfo=IST)
    assert service.next_daily_backstop(now) == datetime(2026, 9, 8, 19, 30, tzinfo=IST)


def test_next_daily_backstop_returns_tomorrow_when_exactly_at_time():
    now = datetime(2026, 9, 7, 19, 30, tzinfo=IST)
    assert service.next_daily_backstop(now) == datetime(2026, 9, 8, 19, 30, tzinfo=IST)


def test_regenerate_brief_writes_content(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(service, "CONTENT_PATH", tmp_path / "daily_brief_content.json")
    monkeypatch.setattr(service, "LAST_ATTEMPT_PATH", tmp_path / "last_attempt.json")
    monkeypatch.setattr(service.portal_archive, "load_archive", lambda: [{"id": "1"}])
    monkeypatch.setattr(
        service.generate_brief, "generate_brief",
        lambda envelope: {"date": "d", "warnings": [], "aviraj_highlight": None,
                           "classwork": [], "homework": ["hw"], "agenda": [],
                           "dress_code": None, "reminders": []},
    )

    portal_poller = service.PortalPoller()
    whatsapp_poller = service.WhatsAppPoller()
    whatsapp_poller.last_messages = [{"sender": "A"}]

    service.regenerate_brief(portal_poller, whatsapp_poller, threading.Lock())

    content = json.loads((tmp_path / "daily_brief_content.json").read_text())
    assert content["homework"] == ["hw"]
    attempt = json.loads((tmp_path / "last_attempt.json").read_text())
    assert attempt["succeeded"] is True


def test_regenerate_brief_records_failure_without_touching_existing_content(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path)
    content_path = tmp_path / "daily_brief_content.json"
    content_path.write_text(json.dumps({"date": "yesterday"}))
    monkeypatch.setattr(service, "CONTENT_PATH", content_path)
    monkeypatch.setattr(service, "LAST_ATTEMPT_PATH", tmp_path / "last_attempt.json")
    monkeypatch.setattr(service.portal_archive, "load_archive", lambda: [])

    def failing_generate(envelope):
        raise RuntimeError("api down")

    monkeypatch.setattr(service.generate_brief, "generate_brief", failing_generate)

    portal_poller = service.PortalPoller()
    whatsapp_poller = service.WhatsAppPoller()

    service.regenerate_brief(portal_poller, whatsapp_poller, threading.Lock())

    assert json.loads(content_path.read_text()) == {"date": "yesterday"}
    attempt = json.loads((tmp_path / "last_attempt.json").read_text())
    assert attempt["succeeded"] is False
    assert "api down" in attempt["error"]


def test_index_shows_placeholder_when_no_brief_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "CONTENT_PATH", tmp_path / "daily_brief_content.json")
    monkeypatch.setattr(service, "LAST_ATTEMPT_PATH", tmp_path / "last_attempt.json")
    client = service.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"No brief generated yet" in response.data


def test_index_renders_latest_brief(tmp_path, monkeypatch):
    content_path = tmp_path / "daily_brief_content.json"
    content_path.write_text(json.dumps({
        "date": "Tuesday, September 08, 2026", "warnings": [], "aviraj_highlight": None,
        "classwork": [], "homework": ["Read pages 10-12"], "agenda": [],
        "dress_code": None, "reminders": [],
    }))
    monkeypatch.setattr(service, "CONTENT_PATH", content_path)
    monkeypatch.setattr(service, "LAST_ATTEMPT_PATH", tmp_path / "last_attempt.json")
    client = service.app.test_client()

    response = client.get("/")

    assert b"Read pages 10-12" in response.data


def test_index_shows_failure_banner_when_last_attempt_failed(tmp_path, monkeypatch):
    content_path = tmp_path / "daily_brief_content.json"
    content_path.write_text(json.dumps({
        "date": "d", "warnings": [], "aviraj_highlight": None, "classwork": [],
        "homework": [], "agenda": [], "dress_code": None, "reminders": [],
    }))
    last_attempt_path = tmp_path / "last_attempt.json"
    last_attempt_path.write_text(json.dumps({
        "succeeded": False, "at": "2026-09-07T19:30:00+05:30", "error": "api down",
    }))
    monkeypatch.setattr(service, "CONTENT_PATH", content_path)
    monkeypatch.setattr(service, "LAST_ATTEMPT_PATH", last_attempt_path)
    client = service.app.test_client()

    response = client.get("/")

    assert b"api down" in response.data
