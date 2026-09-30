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


def is_modifier_key(key):
    return key in MODIFIER_KEYS


def char_of(key):
    """The text character a key produces, or None for non-text keys.

    Space is a text character (so words stay together); Enter/Tab/arrows are not.
    """
    if isinstance(key, keyboard.Key):
        return " " if key == keyboard.Key.space else None
    return getattr(key, "char", None)


def mask_char(ch, mask):
    if not mask or ch.isspace():
        return ch
    if ch.isalpha():
        return "<letter>"
    if ch.isdigit():
        return "<digit>"
    return "<symbol>"


def key_repr(key, mask):
    """Representation for a standalone key/shortcut event (not buffered text)."""
    if isinstance(key, keyboard.Key):
        return key.name
    ch = getattr(key, "char", None)
    if ch is None:
        vk = getattr(key, "vk", None)
        return f"vk{vk}" if vk is not None else "unknown"
    return mask_char(ch, mask)


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
        self.listener = keyboard.Listener(on_press=self._on_press)

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
    def _write_key(self, key, mods):
        title, proc = win32util.get_foreground_info()
        is_hotkey = bool(mods) and not is_modifier_key(key)
        is_char = not isinstance(key, keyboard.Key)
        secured = is_char and not is_hotkey and self.secure.is_secure()
        keytxt = REDACTED if secured else key_repr(key, self.mask_keys)
        combo = ("+".join(mods) + "+" if is_hotkey else "") + keytxt

        event = events.new_event("hotkey" if is_hotkey else "key")
        event["modifiers"] = mods
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

        # Real modifier state from the OS (AltGr excluded), so a missed key-up
        # can't leave a modifier stuck and turn typing into bogus shortcuts.
        mods = win32util.get_modifiers()
        # A "shortcut" needs a command modifier; Shift alone is just typing.
        is_shortcut = any(m in mods for m in ("ctrl", "alt", "win"))

        # Ctrl+Alt+P toggles pause.
        if not isinstance(key, keyboard.Key) and getattr(key, "char", None) in ("p", "\x10") \
           and "ctrl" in mods and "alt" in mods:
            paused = self.st.toggle_pause()
            print(f"--- {'PAUSED' if paused else 'RESUMED'} ---")
            return

        # Skip standalone modifier presses (captured via each event's modifiers).
        if self.st.paused or is_modifier_key(key):
            return

        ch = char_of(key)

        # Backspace edits the running buffer instead of flushing.
        if key == keyboard.Key.backspace and self.aggregate_text and not is_shortcut:
            if self._backspace():
                return

        if ch is not None and not is_shortcut and self.aggregate_text:
            if self.secure.is_secure():
                self.flush_text()
                self._write_key(key, mods)    # logged as redacted <hidden>
            else:
                self._buffer_char(mask_char(ch, self.mask_keys))
            return

        # Structural key / shortcut: flush any pending text, then log it.
        self.flush_text()
        self._write_key(key, mods)
