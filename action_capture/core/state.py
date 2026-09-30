"""Shared pause flag across agents.

Modifier keys are read directly from the OS (see win32util.get_modifiers), so
they are no longer tracked here — only the global pause flag remains.
"""

import threading


class InputState:
    def __init__(self):
        self._lock = threading.Lock()
        self.paused = False

    def toggle_pause(self):
        with self._lock:
            self.paused = not self.paused
            return self.paused
