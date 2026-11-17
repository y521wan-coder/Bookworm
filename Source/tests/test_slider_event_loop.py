from types import SimpleNamespace
from unittest.mock import Mock

import wx

from bookworm.gui.book_viewer import BookViewerWindow


def test_tab_hook_commits_once_through_real_wx_timer(monkeypatch):
    app = wx.GetApp() or wx.App(False)
    frame = wx.Frame(None)
    slider = wx.Slider(frame, value=10, minValue=0, maxValue=100)
    viewer = SimpleNamespace(
        readingProgressSlider=slider,
        _pending_slider_percentage=73,
        _progress_navigation_timer=None,
        _apply_slider_navigation=Mock(),
    )
    viewer._schedule_slider_navigation = lambda *a, **kw: BookViewerWindow._schedule_slider_navigation(viewer, *a, **kw)
    viewer.onSliderKeyDown = lambda event: BookViewerWindow.onSliderKeyDown(viewer, event)
    monkeypatch.setattr(wx.Window, "FindFocus", lambda: slider)
    frame.Bind(wx.EVT_CHAR_HOOK, lambda event: BookViewerWindow.on_key_press_local(viewer, event))
    try:
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(wx.WXK_TAB)
        frame.GetEventHandler().ProcessEvent(event)
        app.SetExitOnFrameDelete(False)
        wx.CallLater(200, app.ExitMainLoop)
        app.MainLoop()
        viewer._apply_slider_navigation.assert_called_once_with(73, True)
    finally:
        frame.Destroy()
