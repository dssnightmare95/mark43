"""Keyboard agent: keystrokes, shortcuts, and typed-text aggregation.

Instead of one row per keypress, consecutive printable characters typed into
the same target are aggregated into a single 'text_input' event ("typed
'hello' in 'chrome.exe'"), which is far more legible for a model. Structural
keys (Enter/Tab/arrows), shortcuts and modifiers flush and are logged on their
own. Password/secure fields are never buffered - their content is omitted.
"""

import threading

from pynput import keyboard

from ..core import events, win32util
from ..labeling.classify import describe_key, describe_text_input

MODIFIER_KEYS = {
    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr,
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
}

FLUSH_IDLE_SEC = 1.5      # flush buffered text after this idle gap
REDACTED = "<hidden>"


def modifier_name(key):
    n = getattr(key, "name", "") or ""
    if n.startswith("ctrl"):
        return "ctrl"
    if n.startswith("alt"):
        return "alt"
    if n.startswith("shift"):
        return "shift"
    if n.startswith("cmd"):
        return "win"
    return ""


def key_repr(key, mask):
    if isinstance(key, keyboard.Key):
        return key.name
    ch = getattr(key, "char", None)
    if ch is None:
        vk = getattr(key, "vk", None)
        return f"vk{vk}" if vk is not None else "unknown"
    if mask:
        if ch.isalpha():
            return "<letter>"
        if ch.isdigit():
            return "<digit>"
        return "<symbol>"
    return ch


class KeyboardAgent:
    def __init__(self, sink, secure_state, input_state, mask_keys=False,
                 aggregate_text=True, on_stop=None):
        self.sink = sink
        self.secure = secure_state
        self.st = input_state
        self.mask_keys = mask_keys
        self.aggregate_text = aggregate_text
        self.on_stop = on_stop
        self._buf = []
        self._buf_meta = None
        self._buf_lock = threading.Lock()
        self._timer = None
        self.listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release)

    def start(self):
        self.listener.start()

    def stop(self):
        self.flush_text()
        self.listener.stop()

    # -- typed-text buffer -------------------------------------------------
    def _restart_timer(self):
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(FLUSH_IDLE_SEC, self.flush_text)
        self._timer.daemon = True
        self._timer.start()

    def flush_text(self):
        """Emit the buffered typed string as one text_input event."""
        with self._buf_lock:
            if not self._buf:
                return
            text = "".join(self._buf)
            meta = self._buf_meta or {}
            self._buf = []
            self._buf_meta = None
        if self._timer:
            self._timer.cancel()
        proc = meta.get("process", "")
        event = events.new_event("text_input")
        event["window"] = meta.get("window", {})
        if self.mask_keys:
            event["key"] = {"length": len(text)}
            event["label"] = f"typed {len(text)} characters in '{proc}'"
        else:
            event["text"] = text
            event["label"] = describe_text_input(text, proc)
        self.sink.write(event)
        print(f"{event['timestamp']}  ->  {event['label']}")

    def _buffer_char(self, ch):
        with self._buf_lock:
            if not self._buf:
                win = win32util.get_window()
                self._buf_meta = {"window": win, "process": win.get("process", "")}
            self._buf.append(ch)
        self._restart_timer()

    def _backspace(self):
        with self._buf_lock:
            if self._buf:
                self._buf.pop()
                return True
        return False

    # -- single key / shortcut events -------------------------------------
    def _write_key(self, key):
        title, proc = win32util.get_foreground_info()
        is_hotkey = self.st.has_mods() and key not in MODIFIER_KEYS
        is_char = not isinstance(key, keyboard.Key)
        secured = is_char and not is_hotkey and self.secure.is_secure()
        keytxt = REDACTED if secured else key_repr(key, self.mask_keys)
        combo = ("+".join(self.st.mods_list()) + "+" if is_hotkey else "") + keytxt

        event = events.new_event("hotkey" if is_hotkey else "key")
        event["modifiers"] = self.st.mods_list()
        event["window"] = {"title": title, "process": proc}
        event["key"] = {"value": keytxt, "combo": combo}
        event["label"] = describe_key(is_hotkey, combo, proc)
        if secured:
            event["secure"] = True
        self.sink.write(event)
        print(f"{event['timestamp']}  ->  {event['label']}")

    # -- handlers ----------------------------------------------------------
    def _on_press(self, key):
        if key == keyboard.Key.esc:
            self.flush_text()
            if self.on_stop:
                self.on_stop()
            return False

        m = modifier_name(key)
        if m:
            self.st.add_mod(m)

        # Ctrl+Alt+P toggles pause.
        if not isinstance(key, keyboard.Key):
            ch = getattr(key, "char", None)
            if ch in ("p", "\x10") and "ctrl" in self.st.mods_list() \
               and "alt" in self.st.mods_list():
                paused = self.st.toggle_pause()
                print(f"--- {'PAUSED' if paused else 'RESUMED'} ---")
                return

        if self.st.paused or m:
            return  # skip standalone modifier presses (captured via 'modifiers')

        is_hotkey = self.st.has_mods()
        is_char = not isinstance(key, keyboard.Key)

        # Backspace edits the running buffer instead of flushing.
        if key == keyboard.Key.backspace and self.aggregate_text and not is_hotkey:
            if self._backspace():
                return

        if is_char and not is_hotkey and self.aggregate_text:
            if self.secure.is_secure():
                self.flush_text()
                self._write_key(key)          # logged as redacted <hidden>
            else:
                self._buffer_char(key_repr(key, self.mask_keys))
            return

        # Structural key / shortcut: flush any pending text, then log it.
        self.flush_text()
        self._write_key(key)

    def _on_release(self, key):
        m = modifier_name(key)
        if m:
            self.st.remove_mod(m)
