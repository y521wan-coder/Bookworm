
"""Speech engine backed by the ZDSR screen-reader API."""

import ctypes
import os
import threading
import time
import winreg
from contextlib import suppress
from ctypes import wintypes
from pathlib import Path

import wx

from bookworm.i18n import LocaleInfo
from bookworm.logger import logger
from bookworm.speechdriver.element.enums import PauseSpec, SpeechElementKind
from bookworm.speechdriver.engine import BaseSpeechEngine, VoiceInfo
from bookworm.speechdriver.enumerations import EngineEvent, SynthState

log = logger.getChild(__name__)

ZDSR_DISPLAY_NAME = "争渡读屏"
ZDSR_CHANNEL_NAME = "飞船阅读"
ZDSR_STATE_SPEAKING = 3
ZDSR_STATE_IDLE = 4
ZDSR_NOT_READY = 9
ZDSR_SUCCESS = 0
POLL_INTERVAL_SECONDS = 0.03
API_DISCOVERY = "API discovery"
CHANNEL_INITIALIZATION = "speech channel initialization"

_api_call_lock = threading.RLock()


class ZdsrError(RuntimeError):
    def __init__(self, operation, error=None):
        detail = f" (error {error})" if error is not None else ""
        super().__init__(f"ZDSR {operation} failed{detail}.")


class ZdsrConfigError(ValueError):
    def __init__(self, setting, value):
        super().__init__(f"Invalid ZDSR {setting}: {value}.")


def _api_filename():
    return "ZDSRAPI_x64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8 else "ZDSRAPI.dll"


def _registry_install_locations():
    uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    access_modes = (winreg.KEY_READ | winreg.KEY_WOW64_32KEY, winreg.KEY_READ)
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for access in access_modes:
            try:
                root = winreg.OpenKey(hive, uninstall_key, 0, access)
            except OSError:
                continue
            with root:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        subkey = winreg.OpenKey(root, subkey_name)
                        with subkey:
                            display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            if display_name != ZDSR_DISPLAY_NAME:
                                continue
                            yield Path(winreg.QueryValueEx(subkey, "InstallLocation")[0])
                    except OSError:
                        continue


def find_zdsr_api():
    """Return the installed ZDSR API DLL, preferring its registered location."""
    filename = _api_filename()
    candidates = list(_registry_install_locations())
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "zdsr" / "zdsr")
    for directory in candidates:
        dll_path = directory / filename
        if dll_path.is_file():
            return dll_path
    return None


def _configure_api(api):
    api.InitTTS.argtypes = (ctypes.c_int, ctypes.c_wchar_p, wintypes.BOOL)
    api.InitTTS.restype = ctypes.c_int
    api.Speak.argtypes = (ctypes.c_wchar_p, wintypes.BOOL)
    api.Speak.restype = ctypes.c_int
    api.GetSpeakState.argtypes = ()
    api.GetSpeakState.restype = ctypes.c_int
    api.StopSpeak.argtypes = ()
    api.StopSpeak.restype = None
    return api


def _pause_milliseconds(value):
    if isinstance(value, PauseSpec):
        return {
            PauseSpec.null: 0,
            PauseSpec.extra_small: 100,
            PauseSpec.small: 250,
            PauseSpec.medium: 500,
            PauseSpec.large: 1000,
            PauseSpec.extra_large: 1500,
        }[value]
    return max(0, int(value))


class ZdsrSpeechEngine(BaseSpeechEngine):
    """Read Bookworm content through ZDSR's independent speech channel."""

    name = "zdsr"
    display_name = "争渡读屏语音库"
    default_rate = 50
    default_pitch = 50
    default_volume = 100

    @classmethod
    def check(cls):
        dll_path = find_zdsr_api()
        if dll_path is None:
            return False
        try:
            _configure_api(ctypes.WinDLL(str(dll_path)))
        except (OSError, AttributeError):
            return False
        return True

    def __init__(self):
        self._dll_path = find_zdsr_api()
        if self._dll_path is None:
            raise ZdsrError(API_DISCOVERY)
        self._api = _configure_api(ctypes.WinDLL(str(self._dll_path)))
        self._lock = threading.RLock()
        self._resume_event = threading.Event()
        self._resume_event.set()
        self._generation = 0
        self._closed = False
        self._owns_speech = False
        self._state = SynthState.ready
        self._voice = self.get_voices()[0]
        self._rate = self.default_rate
        self._pitch = self.default_pitch
        self._volume = self.default_volume
        self.event_handlers = {}
        self._activate_channel()
        self._wait_until_channel_ready()

    def _activate_channel(self):
        with _api_call_lock:
            result = self._api.InitTTS(1, ZDSR_CHANNEL_NAME, False)
        if result != ZDSR_SUCCESS:
            raise ZdsrError("InitTTS", result)

    def _wait_until_channel_ready(self, timeout=3.0):
        deadline = time.monotonic() + timeout
        while True:
            status = self._get_speak_state()
            if status in (ZDSR_STATE_SPEAKING, ZDSR_STATE_IDLE):
                return
            if status != ZDSR_NOT_READY or time.monotonic() >= deadline:
                raise ZdsrError(CHANNEL_INITIALIZATION, status)
            time.sleep(POLL_INTERVAL_SECONDS)

    def _get_speak_state(self):
        with _api_call_lock:
            return self._api.GetSpeakState()

    def _stop_api(self):
        with _api_call_lock:
            self._api.StopSpeak()
        self._owns_speech = False

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            self._resume_event.set()
        if self._owns_speech:
            with suppress(Exception):
                self._stop_api()
        self._state = SynthState.ready

    def get_voices(self):
        return (
            VoiceInfo(
                id="zdsr-current",
                name="ZDSR",
                desc="争渡当前语音",
                language=LocaleInfo("zh_CN"),
            ),
        )

    @property
    def state(self):
        return self._state

    @property
    def voice(self):
        return self._voice

    @voice.setter
    def voice(self, value):
        if value.id != "zdsr-current":
            raise ZdsrConfigError("voice", value.id)
        self._voice = value

    @property
    def rate(self):
        return self._rate

    @rate.setter
    def rate(self, value):
        if not 0 <= value <= 100:
            raise ZdsrConfigError("rate", value)
        self._rate = value

    @property
    def pitch(self):
        return self._pitch

    @pitch.setter
    def pitch(self, value):
        if not 0 <= value <= 100:
            raise ZdsrConfigError("pitch", value)
        self._pitch = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        if not 0 <= value <= 100:
            raise ZdsrConfigError("volume", value)
        self._volume = value

    def speak_utterance(self, utterance):
        actions = self._build_actions(utterance)
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            generation = self._generation
            self._resume_event.set()
        # Normal paragraph handoff must not flush the independent channel.
        # Explicit stop/seek and pause already cancel audio through stop().
        if self._owns_speech:
            self._stop_api()
        self._set_state(SynthState.busy)
        threading.Thread(
            target=self._run_actions,
            args=(generation, actions),
            name="Bookworm-ZDSR",
            daemon=True,
        ).start()

    def _build_actions(self, utterance):
        actions = []
        text_parts = []

        def flush_text():
            text = "".join(text_parts)
            text_parts.clear()
            if text.strip():
                actions.append(("text", text))

        textual_kinds = {
            SpeechElementKind.text,
            SpeechElementKind.sentence,
            SpeechElementKind.ssml,
        }
        for element in utterance:
            if element.kind in textual_kinds:
                text_parts.append(str(element.content))
            elif element.kind is SpeechElementKind.bookmark:
                flush_text()
                actions.append(("bookmark", element.content))
            elif element.kind is SpeechElementKind.pause:
                flush_text()
                duration = _pause_milliseconds(element.content)
                if duration:
                    actions.append(("pause", duration))
        flush_text()
        return actions

    def _run_actions(self, generation, actions):
        try:
            index = 0
            while index < len(actions) and self._is_current(generation):
                if not self._wait_until_resumed(generation):
                    return
                kind, value = actions[index]
                if kind == "bookmark":
                    wx.CallAfter(self._emit_bookmark_if_current, generation, value)
                    index += 1
                elif kind == "pause":
                    if self._wait_for_pause(generation, value / 1000):
                        index += 1
                elif self._speak_text(generation, value):
                    index += 1
        except Exception:
            if self._is_current(generation):
                log.exception("ZDSR speech playback failed")
        finally:
            wx.CallAfter(self._finish_if_current, generation)

    def _speak_text(self, generation, text):
        deadline = time.monotonic() + 1.5
        while self._is_current(generation):
            with self._lock:
                if not self._is_current(generation) or self.state is SynthState.paused:
                    return False
                # Never purge earlier text on a potentially stale idle report.
                with _api_call_lock:
                    result = self._api.Speak(text, False)
                if result == ZDSR_SUCCESS:
                    self._owns_speech = True
                    break
            if result != ZDSR_NOT_READY or time.monotonic() >= deadline:
                raise ZdsrError("Speak", result)
            time.sleep(POLL_INTERVAL_SECONDS)
        idle_seen = False
        while self._is_current(generation):
            with self._lock:
                if not self._is_current(generation) or self.state is SynthState.paused:
                    return False
                status = self._get_speak_state()
                if not self._is_current(generation) or self.state is SynthState.paused:
                    return False
                # Speak is asynchronous: the first query can still report the
                # preceding idle state. Confirm idle on a subsequent poll before
                # emitting bookmarks or starting the next paragraph.
                if status == ZDSR_STATE_IDLE:
                    if idle_seen:
                        self._owns_speech = False
                        return True
                    idle_seen = True
                elif status == ZDSR_STATE_SPEAKING:
                    idle_seen = False
                else:
                    raise ZdsrError("GetSpeakState", status)
            time.sleep(POLL_INTERVAL_SECONDS)
        return False

    def _wait_for_pause(self, generation, seconds):
        deadline = time.monotonic() + seconds
        while self._is_current(generation):
            if self.state is SynthState.paused:
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(POLL_INTERVAL_SECONDS, remaining))
        return False

    def _wait_until_resumed(self, generation):
        while self._is_current(generation):
            if self._resume_event.wait(POLL_INTERVAL_SECONDS):
                return True
        return False

    def _is_current(self, generation):
        with self._lock:
            return not self._closed and generation == self._generation

    def stop(self):
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            self._resume_event.set()
        self._stop_api()
        self._set_state(SynthState.ready)

    def pause(self):
        with self._lock:
            if self._closed or self._state is not SynthState.busy:
                return
            self._resume_event.clear()
            self._set_state(SynthState.paused)
            self._stop_api()

    def resume(self):
        with self._lock:
            if self._closed or self._state is not SynthState.paused:
                return
            self._set_state(SynthState.busy)
            self._resume_event.set()

    def bind(self, event, handler):
        if event not in (EngineEvent.bookmark_reached, EngineEvent.state_changed):
            raise NotImplementedError
        self.event_handlers.setdefault(event, []).append(handler)

    def _set_state(self, new_state):
        self._state = new_state
        for handler in self.event_handlers.get(EngineEvent.state_changed, ()):
            handler(self, new_state)

    def _emit_bookmark_if_current(self, generation, bookmark):
        if not self._is_current(generation):
            return
        for handler in self.event_handlers.get(EngineEvent.bookmark_reached, ()):
            handler(self, bookmark)

    def _finish_if_current(self, generation):
        if self._is_current(generation):
            self._set_state(SynthState.ready)
