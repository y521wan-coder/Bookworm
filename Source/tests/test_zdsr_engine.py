from unittest.mock import Mock

import pytest

from bookworm.platforms.win32.speech_engines import zdsr
from bookworm.speechdriver.element.enums import PauseSpec
from bookworm.speechdriver.enumerations import EngineEvent, SynthState
from bookworm.speechdriver.utterance import SpeechUtterance


class FakeApi:
    def __init__(self):
        self.InitTTS = Mock(return_value=0)
        self.Speak = Mock(return_value=0)
        self.GetSpeakState = Mock(return_value=zdsr.ZDSR_STATE_IDLE)
        self.StopSpeak = Mock()


@pytest.fixture
def engine(monkeypatch, tmp_path):
    dll_path = tmp_path / zdsr._api_filename()
    dll_path.touch()
    api = FakeApi()
    monkeypatch.setattr(zdsr, "find_zdsr_api", lambda: dll_path)
    monkeypatch.setattr(zdsr.ctypes, "WinDLL", lambda _path: api)
    monkeypatch.setattr(zdsr.wx, "CallAfter", lambda func, *args: func(*args))
    instance = zdsr.ZdsrSpeechEngine()
    api.InitTTS.assert_called_once_with(1, zdsr.ZDSR_CHANNEL_NAME, False)
    yield instance, api
    instance.close()


def test_zdsr_utterance_preserves_text_pauses_and_bookmarks(engine):
    instance, _api = engine
    utterance = SpeechUtterance()
    utterance.add_bookmark("start")
    utterance.add_text("第一句")
    utterance.add_pause(PauseSpec.extra_small)
    utterance.add_sentence("第二句")
    utterance.add_bookmark("end")

    assert instance._build_actions(utterance) == [
        ("bookmark", "start"),
        ("text", "第一句"),
        ("pause", 100),
        ("text", "第二句"),
        ("bookmark", "end"),
    ]


def test_zdsr_speaks_and_reports_bookmarks(engine):
    instance, api = engine
    bookmarks = []
    states = []
    instance.bind(EngineEvent.bookmark_reached, lambda _sender, value: bookmarks.append(value))
    instance.bind(EngineEvent.state_changed, lambda _sender, value: states.append(value))
    utterance = SpeechUtterance()
    utterance.add_bookmark("start")
    utterance.add_text("测试")
    utterance.add_bookmark("end")

    actions = instance._build_actions(utterance)
    instance._generation += 1
    generation = instance._generation
    instance._set_state(SynthState.busy)
    instance._run_actions(generation, actions)

    api.Speak.assert_called_once_with("测试", True)
    assert bookmarks == ["start", "end"]
    assert states == [SynthState.busy, SynthState.ready]


def test_zdsr_pause_stops_audio_and_resume_replays_current_text(engine):
    instance, api = engine
    instance._set_state(SynthState.busy)
    instance.pause()

    assert instance.state is SynthState.paused
    assert api.StopSpeak.call_count >= 1

    instance.resume()

    assert instance.state is SynthState.busy


def test_zdsr_exposes_current_configured_voice(engine):
    instance, _api = engine

    assert zdsr.ZDSR_CHANNEL_NAME == "飞船阅读"
    voice = instance.get_voices()[0]
    instance.voice = voice

    assert voice.id == "zdsr-current"
    assert voice.display_name == "争渡当前语音"
