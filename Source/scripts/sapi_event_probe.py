import json
import sys
import time

import comtypes.client
import pythoncom


EVENT_START_INPUT_STREAM = 2
EVENT_END_INPUT_STREAM = 4
EVENT_BOOKMARK = 16
SPF_ASYNC = 1
SPF_IS_XML = 8


class SapiEventSink:
    def __init__(self):
        self.started_at = time.monotonic()
        self.events = []
        self.finished = False

    def _record(self, name, **data):
        elapsed_ms = round((time.monotonic() - self.started_at) * 1000)
        self.events.append({"name": name, "elapsed_ms": elapsed_ms, **data})

    def StartStream(self, stream_num, position):
        self._record("StartStream", stream_number=stream_num, position=position)

    def Bookmark(self, stream_num, position, bookmark, bookmark_id):
        self._record(
            "Bookmark",
            stream_number=stream_num,
            position=position,
            bookmark=bookmark,
            bookmark_id=bookmark_id,
        )

    def EndStream(self, stream_num, position):
        self._record("EndStream", stream_number=stream_num, position=position)
        self.finished = True


def find_voice(voice, suffix):
    tokens = voice.GetVoices()
    for index in range(tokens.Count):
        token = tokens.Item(index)
        if token.Id.lower().endswith(suffix.lower()):
            return token
    raise LookupError(f"Voice token not found: {suffix}")


def main():
    suffix = sys.argv[1]
    voice = comtypes.client.CreateObject("SAPI.SPVoice")
    voice.Voice = find_voice(voice, suffix)

    sink = SapiEventSink()
    event_connection = comtypes.client.GetEvents(voice, sink)
    voice.EventInterests = (
        EVENT_START_INPUT_STREAM | EVENT_END_INPUT_STREAM | EVENT_BOOKMARK
    )

    xml = (
        '<xml version="1.0"><pitch absmiddle="0">'
        "\u8fd9\u662f\u7b2c\u4e00\u53e5\u3002"
        '<bookmark mark="first_end"/>'
        "\u8fd9\u662f\u7b2c\u4e8c\u53e5\u3002"
        '<bookmark mark="second_end"/>'
        '<silence msec="5"/></pitch></xml>'
    )
    voice.Speak(xml, SPF_ASYNC | SPF_IS_XML)

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not sink.finished:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.01)

    print(
        json.dumps(
            {
                "voice": voice.Voice.GetDescription(),
                "running_state": voice.Status.RunningState,
                "finished": sink.finished,
                "events": sink.events,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    del event_connection


if __name__ == "__main__":
    main()
