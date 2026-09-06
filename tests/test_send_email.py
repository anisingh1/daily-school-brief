import pytest

import send_email


def test_send_brief_email_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(send_email, "SMTP_USERNAME", None)
    monkeypatch.setattr(send_email, "SMTP_APP_PASSWORD", None)
    monkeypatch.setattr(send_email, "EMAIL_TO", None)
    with pytest.raises(RuntimeError):
        send_email.send_brief_email("subject", "<p>body</p>")


def test_send_brief_email_sends_via_smtp(monkeypatch):
    monkeypatch.setattr(send_email, "SMTP_USERNAME", "me@gmail.com")
    monkeypatch.setattr(send_email, "SMTP_APP_PASSWORD", "app-pass")
    monkeypatch.setattr(send_email, "EMAIL_TO", "family@gmail.com")

    calls = {}

    class FakeSMTP:
        def __init__(self, host, port):
            calls["host"] = host
            calls["port"] = port

        def __enter__(self):
            calls.setdefault("sequence", []).append("enter")
            return self

        def __exit__(self, *args):
            calls.setdefault("sequence", []).append("exit")
            return False

        def login(self, username, password):
            calls.setdefault("sequence", []).append("login")
            calls["login"] = (username, password)

        def sendmail(self, from_addr, to_addrs, msg):
            calls.setdefault("sequence", []).append("sendmail")
            calls["sendmail"] = (from_addr, to_addrs)
            calls["msg_contains_html"] = "<p>body</p>" in msg

    monkeypatch.setattr(send_email.smtplib, "SMTP_SSL", FakeSMTP)

    send_email.send_brief_email("Test Subject", "<p>body</p>")

    assert calls["host"] == "smtp.gmail.com"
    assert calls["port"] == 465
    assert calls["login"] == ("me@gmail.com", "app-pass")
    assert calls["sendmail"] == ("me@gmail.com", ["family@gmail.com"])
    assert calls["msg_contains_html"] is True
    assert calls["sequence"] == ["enter", "login", "sendmail", "exit"]


def test_send_brief_email_splits_comma_separated_recipients(monkeypatch):
    monkeypatch.setattr(send_email, "SMTP_USERNAME", "me@gmail.com")
    monkeypatch.setattr(send_email, "SMTP_APP_PASSWORD", "app-pass")
    monkeypatch.setattr(send_email, "EMAIL_TO", "family@gmail.com, other@gmail.com")

    calls = {}

    class FakeSMTP:
        def __init__(self, host, port):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, username, password):
            pass

        def sendmail(self, from_addr, to_addrs, msg):
            calls["sendmail"] = (from_addr, to_addrs)

    monkeypatch.setattr(send_email.smtplib, "SMTP_SSL", FakeSMTP)

    send_email.send_brief_email("Test Subject", "<p>body</p>")

    assert calls["sendmail"] == (
        "me@gmail.com",
        ["family@gmail.com", "other@gmail.com"],
    )


def test_run_reads_content_renders_and_sends(tmp_path, monkeypatch):
    monkeypatch.setattr(send_email, "CONTENT_PATH", tmp_path / "daily_brief_content.json")
    (tmp_path / "daily_brief_content.json").write_text(
        '{"date": "2026-09-05", "warnings": [], "aviraj_highlight": null, '
        '"homework": [], "agenda": [], "dress_code": null, "reminders": []}'
    )

    calls = {}
    monkeypatch.setattr(send_email, "render_brief_html", lambda data: "<html>fake</html>")
    monkeypatch.setattr(
        send_email,
        "send_brief_email",
        lambda subject, html: calls.update({"subject": subject, "html": html}),
    )

    send_email.run()

    assert calls["subject"] == "Daily School Brief - 2026-09-05"
    assert calls["html"] == "<html>fake</html>"
