# coding: utf-8

"""Screen reader and braille output."""

import shutil
import win32com
from accessible_output2.outputs.auto import Auto

from bookworm import config
from bookworm.logger import logger
from bookworm.signals import reading_position_change

log = logger.getChild(__name__)


_auto_output = None
_auto_output_unavailable = False


def announce(message, urgent=False):
    """Speak and braille a message related to UI."""
    global _auto_output, _auto_output_unavailable
    if not config.conf["general"]["announce_ui_messages"]:
        return
    if _auto_output_unavailable:
        return
    if _auto_output is None:
        try:
            _auto_output = Auto()
        except (AttributeError, ImportError):
            shutil.rmtree(win32com.__gen_path__, ignore_errors=True)
            try:
                _auto_output = Auto()
            except Exception:
                _auto_output_unavailable = True
                log.exception("Failed to initialize screen reader output")
                return
        except Exception:
            _auto_output_unavailable = True
            log.exception("Failed to initialize screen reader output")
            return
    try:
        _auto_output.speak(message, interrupt=urgent)
        _auto_output.braille(message)
    except Exception:
        log.exception("Failed to announce a user interface message")


@reading_position_change.connect
def announce_new_reading_position(sender, position, **kwargs):
    if text_to_announce := kwargs.get("text_to_announce"):
        announce(text_to_announce, urgent=True)
