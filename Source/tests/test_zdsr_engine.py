from unittest.mock import Mock, call

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

    api.Speak.assert_called_once_with("测试", False)
    assert bookmarks == ["start", "end"]
    assert states == [SynthState.busy, SynthState.ready]


def test_zdsr_zero_pauses_preserve_default_sentence_boundaries(engine):
    instance, api = engine
    utterance = SpeechUtterance()
    utterance.add_sentence("第一句。")
    utterance.add_pause(0)
    utterance.add_sentence("第二句。”")

    actions = instance._build_actions(utterance)
    assert actions == [("text", "第一句。"), ("text", "第二句。”")]
    instance._generation += 1
    generation = instance._generation
    instance._set_state(SynthState.busy)
    instance._run_actions(generation, actions)

    assert api.Speak.call_args_list == [call("第一句。", False), call("第二句。”", False)]


def test_zdsr_preserves_decimal_points_and_other_punctuation(engine):
    instance, _api = engine
    utterance = SpeechUtterance()
    utterance.add_sentence("数值3.14，确定吗？")
    utterance.add_sentence("英文句末.")
    utterance.add_sentence("全角句末．")

    assert instance._build_actions(utterance) == [
        ("text", "数值3.14，确定吗？英文句末.全角句末．"),
    ]


@pytest.mark.parametrize("sentence_pause", [0, 100])
def test_reading_service_preserves_default_sentences_without_synthetic_dot(engine, sentence_pause):
    from collections import deque
    from types import SimpleNamespace

    from bookworm.text_to_speech import TextToSpeechService
    from bookworm.structured_text import TextInfo

    instance, api = engine
    paragraph = "今天的天气很好。我们一起去散步。他说：“走吧。”然后推开了门。"
    service = object.__new__(TextToSpeechService)
    service.engine = instance
    service._speech_session = 1
    service.utterance_queue = deque()
    service.reader = SimpleNamespace(
        document=SimpleNamespace(is_single_page_document=lambda: False)
    )
    service.config_manager = {"sentence_pause": sentence_pause, "paragraph_pause": 300}
    info = TextInfo(paragraph, lang="zh")
    service.add_text_utterances(info)
    utterance = service.utterance_queue.pop()
    actions = instance._build_actions(utterance)
    sentences = list(info.split_sentences(paragraph))
    assert [v for k, v in actions if k == "text"] == [s + " " for s in sentences]
    expected_pauses = [sentence_pause] * len(sentences) if sentence_pause else []
    assert [v for k, v in actions if k == "pause"] == expected_pauses + [300]
    instance._emit_bookmark_if_current = Mock()
    instance._wait_for_pause = Mock(return_value=True)
    instance._run_actions(instance._generation, actions)
    assert api.Speak.call_args_list == [call(s + " ", False) for s in sentences]
    assert all(args[0] != "\n." for args, _kwargs in api.Speak.call_args_list)


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


def test_zdsr_initial_idle_does_not_advance_to_next_sentence(engine, monkeypatch):
    instance, api = engine
    instance._set_state(SynthState.busy)
    # Real DLL trace: Speak succeeds, then idle precedes speaking.
    states = iter([4, 3, 3, 4, 4])
    observed = []
    def state():
        value = next(states)
        observed.append(value)
        return value
    api.GetSpeakState.side_effect = state
    monkeypatch.setattr(zdsr.time, "sleep", lambda _seconds: None)
    assert instance._speak_text(instance._generation, "first sentence")
    assert observed == [4, 3, 3, 4, 4]
    api.Speak.assert_called_once_with("first sentence", False)


def test_zdsr_paragraph_handoff_does_not_clear_api_queue(engine, monkeypatch):
    instance, api = engine
    monkeypatch.setattr(zdsr.threading, "Thread", Mock())
    utterance = SpeechUtterance()
    utterance.add_text("next paragraph")
    instance.speak_utterance(utterance)
    api.StopSpeak.assert_not_called()


def test_zdsr_pause_during_state_query_does_not_complete_text(engine):
    instance, api = engine
    instance._set_state(SynthState.busy)
    def state():
        instance.pause()
        return zdsr.ZDSR_STATE_IDLE
    api.GetSpeakState.side_effect = state
    assert not instance._speak_text(instance._generation, "unfinished sentence")
    assert instance.state is SynthState.paused


def test_zdsr_stale_idle_never_discards_queued_sentences(engine, monkeypatch):
    instance, api = engine
    # Even an idle report lasting several polls must not cause data loss.
    pending = []
    def speak(text, interrupt):
        if interrupt:
            pending.clear()
        pending.append(text)
        return 0
    api.Speak.side_effect = speak
    api.StopSpeak.side_effect = pending.clear
    monkeypatch.setattr(zdsr.time, "sleep", lambda _seconds: None)
    class InlineThread:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(zdsr.threading, "Thread", InlineThread)
    for paragraph in range(3):
        utterance = SpeechUtterance()
        for sentence in range(3):
            utterance.add_text(f"{paragraph}:{sentence}")
            utterance.add_pause(0)
        instance.speak_utterance(utterance)
    assert pending == [f"{p}:{s}" for p in range(3) for s in range(3)]
    instance.stop()
    assert pending == []


def test_zdsr_cancelled_worker_cannot_submit_text(engine):
    instance, api = engine
    generation = instance._generation
    instance.stop()
    assert not instance._speak_text(generation, "cancelled")
    api.Speak.assert_not_called()
