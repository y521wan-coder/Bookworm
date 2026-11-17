import weakref
from unittest.mock import Mock, call

from bookworm.platforms.win32.speech_engines.sapi._sapi import (
    SPAudioState,
    SapiEventSink,
    SapiSpeechEngine,
)
from bookworm.speechdriver.enumerations import SynthState


def test_repeated_pause_resume_survives_delayed_stream_events():
    engine = object.__new__(SapiSpeechEngine)
    engine.event_handlers = {}
    engine.tts = Mock()
    engine.tts_audio_stream = Mock()
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
    engine.tts.Pause.assert_not_called()
    engine.tts.Resume.assert_not_called()
    assert engine.tts_audio_stream.setState.call_args_list == [
        item
        for _ in range(5)
        for item in (
            call(SPAudioState.Paused, 0),
            call(SPAudioState.Running, 0),
        )
    ]
