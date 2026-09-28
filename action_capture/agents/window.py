"""Window agent: detects foreground/app focus changes.

Polls the foreground window and emits a 'window_focus' event whenever it
changes (Alt+Tab, launching an app, switching documents). These events mark
the boundaries between subtasks. On every focus change it also flushes any
pending typed-text buffer, so text is attributed to the window it was typed in.
"""

import threading

from ..core import events, win32util


class WindowAgent(threading.Thread):
    def __init__(self, sink, input_state, on_focus_change=None, interval=0.25):
        super().__init__(daemon=True)
        self.sink = sink
        self.st = input_state
        self.on_focus_change = on_focus_change
        self.interval = interval
        self._stop = threading.Event()
        self._last_hwnd = None

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.wait(self.interval):
            if self.st.paused:
                continue
            try:
                hwnd = win32util.get_active_hwnd()
            except Exception:
                continue
            if not hwnd or hwnd == self._last_hwnd:
                continue
            self._last_hwnd = hwnd
            # Focus changed: flush typed text to the previous window first.
            if self.on_focus_change:
                try:
                    self.on_focus_change()
                except Exception:
                    pass
            win = win32util.get_window(hwnd)
            event = events.new_event("window_focus")
            event["window"] = win
            title = win.get("title", "")
            proc = win.get("process", "")
            event["label"] = f"focus changed to '{title}' [{proc}]"
            self.sink.write(event)
            print(f"{event['timestamp']}  ->  {event['label']}")
