import json

import google_drive


def test_build_client_uses_file_path_branch(monkeypatch, tmp_path):
    key_file = tmp_path / "key.json"
    key_file.write_text("{}")
    calls = {}

    def fake_from_file(path, scopes):
        calls["file_path"] = path
        return "fake-creds-from-file"

    def fake_build(service, version, credentials):
        calls["credentials"] = credentials
        return "fake-client"

    monkeypatch.setattr(
        google_drive.service_account.Credentials, "from_service_account_file", fake_from_file
    )
    monkeypatch.setattr(google_drive, "build", fake_build)

    result = google_drive.build_client(str(key_file))

    assert result == "fake-client"
    assert calls["file_path"] == str(key_file)
    assert calls["credentials"] == "fake-creds-from-file"


def test_build_client_uses_raw_json_branch(monkeypatch):
    raw_json = json.dumps({"type": "service_account"})
    calls = {}

    def fake_from_info(info, scopes):
        calls["info"] = info
        return "fake-creds-from-info"

    def fake_build(service, version, credentials):
        calls["credentials"] = credentials
        return "fake-client"

    monkeypatch.setattr(
        google_drive.service_account.Credentials, "from_service_account_info", fake_from_info
    )
    monkeypatch.setattr(google_drive, "build", fake_build)

    result = google_drive.build_client(raw_json)

    assert result == "fake-client"
    assert calls["info"] == {"type": "service_account"}
    assert calls["credentials"] == "fake-creds-from-info"
