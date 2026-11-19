import weakref
from unittest.mock import Mock

from bookworm.platforms.win32.speech_engines.sapi._sapi import (
    SPAudioState,
    SapiEventSink,
    SapiSpeechEngine,
)
from bookworm.speechdriver.enumerations import SynthState


class StrictAudioStream:
    """Expose only the method name declared by the frozen COM interface."""

    def __init__(self):
        self.calls = []

    def SetState(self, state, reserved):
        self.calls.append((state, reserved))


def test_repeated_pause_resume_survives_delayed_stream_events():
    engine = object.__new__(SapiSpeechEngine)
    engine.event_handlers = {}
    engine.tts = Mock()
    engine.tts_audio_stream = StrictAudioStream()
    engine._current_stream = 1
    engine._stream_received_bookmarks = set()
    engine._recover_missing_bookmarks = Mock()
    engine._set_state(SynthState.busy)
    sink = SapiEventSink(weakref.ref(engine))
    for _ in range(5):
        engine.pause()
        assert engine.state is SynthState.paused
        sink.StartStream(1, 0)
        sink.EndStream(1, 0)
        assert engine.state is SynthState.paused
        engine.resume()
        assert engine.state is SynthState.busy
    assert engine.tts.Pause.call_count == 5
    assert engine.tts.Resume.call_count == 5
    assert engine.tts_audio_stream.calls == [
        item
        for _ in range(5)
        for item in (
            (SPAudioState.Paused, 0),
            (SPAudioState.Running, 0),
        )
    ]


def test_pause_state_is_visible_to_stream_events_before_audio_call():
    engine = object.__new__(SapiSpeechEngine)
    engine.event_handlers = {}
    engine.tts = Mock()
    engine._current_stream = 1
    engine._stream_received_bookmarks = set()
    engine._recover_missing_bookmarks = Mock()
    engine._set_state(SynthState.busy)
    sink = SapiEventSink(weakref.ref(engine))

    class EventingAudioStream(StrictAudioStream):
        def SetState(self, state, reserved):
            sink.StartStream(1, 0)
            sink.EndStream(1, 0)
            super().SetState(state, reserved)

    engine.tts_audio_stream = EventingAudioStream()
    engine.pause()

    assert engine.state is SynthState.paused

def test_previous_stream_end_cannot_advance_current_paragraph():
    engine = object.__new__(SapiSpeechEngine)
    engine.event_handlers = {}
    engine._current_stream = 2
    engine._stream_received_bookmarks = {"current"}
    engine._recover_missing_bookmarks = Mock()
    engine._set_state(SynthState.busy)
    sink = SapiEventSink(weakref.ref(engine))
    sink.StartStream(1, 0)
    sink.Bookmark(1, 0, "old", 0)
    sink.EndStream(1, 0)
    assert engine.state is SynthState.busy
    assert engine._stream_received_bookmarks == {"current"}
    engine._recover_missing_bookmarks.assert_not_called()
    sink.EndStream(2, 0)
    engine._recover_missing_bookmarks.assert_called_once_with()
