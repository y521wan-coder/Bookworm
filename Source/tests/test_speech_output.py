from unittest.mock import Mock

from bookworm import speech


def _enable_announcements(monkeypatch):
    monkeypatch.setattr(
        speech.config,
        "conf",
        {"general": {"announce_ui_messages": True}},
    )
    monkeypatch.setattr(speech, "_auto_output", None)
    monkeypatch.setattr(speech, "_auto_output_unavailable", False)


def test_announce_retries_output_initialization_without_exiting(monkeypatch):
    _enable_announcements(monkeypatch)
    output = Mock()
    auto = Mock(side_effect=[AttributeError("stale COM cache"), output])
    remove_cache = Mock()
    monkeypatch.setattr(speech, "Auto", auto)
    monkeypatch.setattr(speech.shutil, "rmtree", remove_cache)

    speech.announce("Paused", urgent=True)

    assert auto.call_count == 2
    remove_cache.assert_called_once_with(speech.win32com.__gen_path__, ignore_errors=True)
    output.speak.assert_called_once_with("Paused", interrupt=True)
    output.braille.assert_called_once_with("Paused")


def test_announce_failure_does_not_close_the_application(monkeypatch):
    _enable_announcements(monkeypatch)
    monkeypatch.setattr(speech, "Auto", Mock(side_effect=RuntimeError("unavailable")))
    log_exception = Mock()
    monkeypatch.setattr(speech.log, "exception", log_exception)

    speech.announce("Paused")
    speech.announce("Resumed")

    assert speech._auto_output_unavailable is True
    log_exception.assert_called_once_with("Failed to initialize screen reader output")
