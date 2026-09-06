import subprocess

import commit_archive


def _completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_skips_commit_when_nothing_staged(monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args)
        if args[:2] == ["git", "diff"]:
            return _completed(0)  # nothing staged
        return _completed(0)

    monkeypatch.setattr(commit_archive, "_run", fake_run)

    commit_archive.commit_and_push()

    commands = [c[:2] for c in calls]
    assert ["git", "add"] in commands
    assert ["git", "commit"] not in commands
    assert ["git", "push"] in commands


def test_commits_when_changes_staged(monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args)
        if args[:2] == ["git", "diff"]:
            return _completed(1)  # changes staged
        return _completed(0)

    monkeypatch.setattr(commit_archive, "_run", fake_run)

    commit_archive.commit_and_push()

    commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
    assert len(commit_calls) == 1
    assert commit_calls[0] == ["git", "commit", "-m", "Update portal archive"]


def test_reports_warning_on_push_failure_without_raising(monkeypatch, capsys):
    def fake_run(args):
        if args[:2] == ["git", "diff"]:
            return _completed(0)
        if args[:2] == ["git", "push"]:
            return _completed(1, stderr="! [rejected] main -> main (non-fast-forward)")
        return _completed(0)

    monkeypatch.setattr(commit_archive, "_run", fake_run)

    commit_archive.commit_and_push()  # must not raise

    assert "non-fast-forward" in capsys.readouterr().out


def test_raises_on_add_failure(monkeypatch):
    def fake_run(args):
        if args[:2] == ["git", "add"]:
            return _completed(1, stderr="fatal: not a git repository")
        return _completed(0)

    monkeypatch.setattr(commit_archive, "_run", fake_run)

    try:
        commit_archive.commit_and_push()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "add" in str(e)


def test_raises_on_commit_failure(monkeypatch):
    def fake_run(args):
        if args[:2] == ["git", "diff"]:
            return _completed(1)  # changes staged
        if args[:2] == ["git", "commit"]:
            return _completed(1, stderr="fatal: unable to write commit")
        return _completed(0)

    monkeypatch.setattr(commit_archive, "_run", fake_run)

    try:
        commit_archive.commit_and_push()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "commit" in str(e)
