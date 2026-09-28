"""Password/secure-field latch: never log the content typed into secrets."""

import threading

from .win32util import focused_is_password_win32


class SecureState:
    """Is the current input target a password field?

    Two layers: a latch set asynchronously by the UI-context agent whenever a
    click resolves onto an element (True if that element is a password field),
    plus the synchronous Win32 ES_PASSWORD check for native controls.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._from_click = False

    def set_from_click(self, value):
        with self._lock:
            self._from_click = bool(value)

    def is_secure(self):
        with self._lock:
            latched = self._from_click
        return latched or focused_is_password_win32()
