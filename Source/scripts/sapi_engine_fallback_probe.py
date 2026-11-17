import json
import time

import pythoncom

from bookworm.platforms.win32.speech_engines.sapi._sapi import SapiSpeechEngine
from bookworm.speechdriver.enumerations import EngineEvent
from bookworm.speechdriver.utterance import SpeechUtterance


def main():
    received = []
    engine = SapiSpeechEngine()
    engine.set_voice_from_string(
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\AiSound_XiaoFeng"
    )
    engine.bind(
        EngineEvent.bookmark_reached,
        lambda sender, bookmark: received.append(bookmark),
    )

    utterance = SpeechUtterance()
    utterance.add_text("\u8fd9\u662f\u4e00\u6b21\u56de\u9000\u6d4b\u8bd5\u3002")
    utterance.add_bookmark("probe_end")
    utterance.add_pause(5)
    engine.speak(utterance)

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and "probe_end" not in received:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.01)

    print(
        json.dumps(
            {
                "voice": engine.voice.display_name,
                "bookmarks": received,
                "fallback_worked": "probe_end" in received,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    engine.close()


if __name__ == "__main__":
    main()
