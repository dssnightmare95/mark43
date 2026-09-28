"""Input state shared across agents (modifier keys held, pause flag)."""

import threading


class InputState:
    """Modifier keys currently held + global pause flag.

    The keyboard agent maintains the modifier set; the mouse agent reads it so
    each gesture records the modifiers active at the time.
    """

    _ORDER = ["ctrl", "alt", "shift", "win"]

    def __init__(self):
        self._lock = threading.Lock()
        self.active_mods = set()
        self.paused = False

    def add_mod(self, name):
        if name:
            with self._lock:
                self.active_mods.add(name)

    def remove_mod(self, name):
        if name:
            with self._lock:
                self.active_mods.discard(name)

    def mods_list(self):
        with self._lock:
            return [m for m in self._ORDER if m in self.active_mods]

    def has_mods(self):
        with self._lock:
            return bool(self.active_mods)

    def toggle_pause(self):
        with self._lock:
            self.paused = not self.paused
            return self.paused
