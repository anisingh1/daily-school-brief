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
