# coding: utf-8

from .sapi import SapiSpeechEngine
from .zdsr import ZdsrSpeechEngine

TTS_ENGINES = (SapiSpeechEngine,)

if ZdsrSpeechEngine.check():
    TTS_ENGINES = (*TTS_ENGINES, ZdsrSpeechEngine)


try:
    from .onecore import OcSpeechEngine
except:
    pass
else:
    if OcSpeechEngine.check():
        TTS_ENGINES = (OcSpeechEngine, *TTS_ENGINES)

try:
    from .piper import PiperSpeechEngine
except:
    raise
else:
    if PiperSpeechEngine.check():
        TTS_ENGINES = (*TTS_ENGINES, PiperSpeechEngine)

try:
    from .espeak import ESpeakSpeechEngine
except FileExistsError:
    pass
except:
    raise
else:
    if ESpeakSpeechEngine.check():
        TTS_ENGINES = (
            *TTS_ENGINES,
            PiperSpeechEngine,
            ESpeakSpeechEngine,
        )
